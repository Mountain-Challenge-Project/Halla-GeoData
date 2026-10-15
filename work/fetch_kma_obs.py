"""Stage 1b: collect KMA surface observations for the Jeju stations (the model's ground truth).

  python work/fetch_kma_obs.py                  current AWS minute values + the last complete ASOS hour
  python work/fetch_kma_obs.py --asos-backfill 2023-01-01   ASOS hourly history in 31-day chunks (kma_sfctm3)

Sources (API Hub, all approved on 2026-10-15/16):
  AWS 매분자료  nph-aws2_min  (tm2=YYYYMMDDHHMI, stn=0) : 1-min T, RH, Td, PA, PS, 10-min wind, 15/60-min rain
  ASOS 시간자료 kma_sfctm2    (tm=YYYYMMDDHH00, stn=0)   : hourly synoptic incl. Td, PA/PS, cloud, visibility, SI
  ASOS 기간자료 kma_sfctm3    (tm1, tm2 <= 31 days)       : the same columns for backfill

Outputs (local only, gitignored except obs_latest.json):
  runtime/kma/obs/aws_min/YYYYMM.csv     appended rows (one per station per fetch)
  runtime/kma/obs/asos_hourly/YYYYMM.csv appended / backfilled rows
  outputs/jeju_dashboard/data/obs_latest.json  latest value per station with its 500 m cell, for the dashboard
Missing values are KMA's -99.x / -9.x codes and are written as empty cells.
"""
import csv, json, sys, time, datetime as dt, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_kma_forecast import key_from_env, get, KST, ROOT  # noqa: E402

T = 'https://apihub.kma.go.kr/api/typ01/'
AWS_COLS = ['TM', 'STN', 'WD1', 'WS1', 'WDS', 'WSS', 'WD10', 'WS10', 'TA', 'RE', 'RN_15M', 'RN_60M', 'RN_12H', 'RN_DAY', 'HM', 'PA', 'PS', 'TD']
ASOS_COLS = ['TM', 'STN', 'WD', 'WS', 'GST_WD', 'GST_WS', 'GST_TM', 'PA', 'PS', 'PT', 'PR', 'TA', 'TD', 'HM', 'PV', 'RN', 'RN_DAY', 'RN_JUN', 'RN_INT',
             'SD_HR3', 'SD_DAY', 'SD_TOT', 'WC', 'WP', 'WW', 'CA_TOT', 'CA_MID', 'CH_MIN', 'CT', 'CT_TOP', 'CT_MID', 'CT_LOW', 'VS', 'SS', 'SI', 'ST_GD', 'TS',
             'TE_005', 'TE_01', 'TE_02', 'TE_03', 'ST_SEA', 'WH', 'BF', 'IR', 'IX']
OBS = ROOT / 'runtime/kma/obs'


def decode(raw):
    try: return raw.decode('utf-8')
    except UnicodeDecodeError: return raw.decode('cp949', 'replace')


def fetch(url, params, key, tries=4):
    for i in range(tries):
        try:
            code, body = get(url, params, key, 180)
            return decode(body)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            code = getattr(e, 'code', None)
            if i < tries - 1 and (code in (502, 503, 504, None)): time.sleep(5 * (i + 1)); continue
            raise


def clean(v):
    try: x = float(v)
    except ValueError: return v if v not in ('-', '') else ''
    return '' if x <= -9 and v.startswith('-9') else v


def parse_rows(text, cols, stations):
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'): continue
        parts = line.split()
        if len(parts) < 3 or parts[1] not in stations: continue
        rec = {c: clean(parts[i]) if i < len(parts) else '' for i, c in enumerate(cols)}
        rows.append(rec)
    return rows


def append_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    seen = set()
    if not new:
        with path.open(encoding='utf-8') as f:
            for r in csv.DictReader(f): seen.add((r['TM'], r['STN']))
    added = 0
    with path.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new: w.writeheader()
        for r in rows:
            if (r['TM'], r['STN']) in seen: continue
            w.writerow(r); seen.add((r['TM'], r['STN'])); added += 1
    return added


def load_stations():
    p = ROOT / 'inputs/reference/kma_stations_jeju.csv'
    if not p.exists(): raise SystemExit('run work/fetch_kma_stations.py first')
    with p.open(encoding='utf-8-sig') as f:
        return {r['stn']: r for r in csv.DictReader(f)}


def write_latest(stations, aws_rows, asos_rows):
    latest = {}
    for r in aws_rows:
        s = stations[r['STN']]
        latest[r['STN']] = {'name': s['name'], 'kind': s['kind'], 'lon': float(s['lon']), 'lat': float(s['lat']), 'ht_m': float(s['ht_m']) if s['ht_m'] else None,
                            'grid_id': s['grid_id'] or None, 'tm': r['TM'], 'ta': r['TA'], 'td': r['TD'], 'hm': r['HM'], 'pa': r['PA'], 'ps': r['PS'],
                            'wd10': r['WD10'], 'ws10': r['WS10'], 'wss': r['WSS'], 'rn60': r['RN_60M'], 'rn_day': r['RN_DAY'], 'source': 'aws_min'}
    for r in asos_rows:
        d = latest.setdefault(r['STN'], {'name': stations[r['STN']]['name'], 'kind': 'SFC', 'lon': float(stations[r['STN']]['lon']), 'lat': float(stations[r['STN']]['lat']),
                                         'ht_m': float(stations[r['STN']]['ht_m'] or 0), 'grid_id': stations[r['STN']]['grid_id'] or None, 'source': 'asos_hourly'})
        d['asos'] = {'tm': r['TM'], 'ta': r['TA'], 'td': r['TD'], 'hm': r['HM'], 'pa': r['PA'], 'ps': r['PS'], 'pt': r['PT'], 'pr': r['PR'], 'ca_tot': r['CA_TOT'],
                     'ch_min': r['CH_MIN'], 'vs': r['VS'], 'si': r['SI'], 'ww': r['WW']}
    doc = {'schema_version': 1, 'fetched_at': dt.datetime.now(KST).isoformat(), 'station_count': len(latest), 'stations': latest,
           'source': 'KMA API Hub nph-aws2_min (1-min) + kma_sfctm2 (hourly ASOS); missing = null/empty', 'note': '지점 관측값은 그 지점이 속한 500 m 셀의 정답 자료로만 쓰며 보간하지 않음'}
    (ROOT / 'outputs/jeju_dashboard/data/obs_latest.json').write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return doc


def main(argv):
    key = key_from_env()
    if not key: raise SystemExit('.env의 KMA_API_KEY가 비어 있습니다')
    stations = load_stations(); now = dt.datetime.now(KST)
    if '--asos-backfill' in argv:
        start = dt.datetime.strptime(argv[argv.index('--asos-backfill') + 1], '%Y-%m-%d').replace(tzinfo=KST)
        asos_ids = [s for s, r in stations.items() if r['kind'] == 'SFC']
        total = 0; t1 = start
        while t1 < now:
            t2 = min(t1 + dt.timedelta(days=30, hours=23), now)
            text = fetch(T + 'url/kma_sfctm3.php', {'tm1': t1.strftime('%Y%m%d%H%M'), 'tm2': t2.strftime('%Y%m%d%H%M'), 'stn': ':'.join(asos_ids), 'help': '0'}, key)
            rows = parse_rows(text, ASOS_COLS, stations)
            by_month = {}
            for r in rows: by_month.setdefault(r['TM'][:6], []).append(r)
            added = sum(append_csv(OBS / 'asos_hourly' / f'{m}.csv', rs, ASOS_COLS) for m, rs in by_month.items())
            total += added; print(f'  {t1:%Y-%m-%d} .. {t2:%Y-%m-%d}: {len(rows)} rows, {added} new', flush=True)
            t1 = t2 + dt.timedelta(hours=1); time.sleep(1)
        print('ASOS_BACKFILL_DONE', total); return 0
    # current AWS minute values (one row per station) and the last complete ASOS hour
    tm2 = (now - dt.timedelta(minutes=3)).strftime('%Y%m%d%H%M')
    aws_text = fetch(T + 'cgi-bin/url/nph-aws2_min', {'tm2': tm2, 'stn': '0', 'disp': '0', 'help': '0'}, key)
    aws_rows = parse_rows(aws_text, AWS_COLS, stations)
    tm_h = (now - dt.timedelta(minutes=10)).strftime('%Y%m%d%H00')
    asos_text = fetch(T + 'url/kma_sfctm2.php', {'tm': tm_h, 'stn': '0', 'help': '0'}, key)
    asos_rows = parse_rows(asos_text, ASOS_COLS, stations)
    a1 = append_csv(OBS / 'aws_min' / f'{tm2[:6]}.csv', aws_rows, AWS_COLS)
    a2 = append_csv(OBS / 'asos_hourly' / f'{tm_h[:6]}.csv', asos_rows, ASOS_COLS)
    doc = write_latest(stations, aws_rows, asos_rows)
    hi = max((s for s in doc['stations'].values() if s.get('ta')), key=lambda s: s['ht_m'] or 0, default=None)
    print('OBS_WRITTEN', json.dumps({'tm_aws': tm2, 'aws_stations': len(aws_rows), 'aws_new_rows': a1, 'tm_asos': tm_h, 'asos_stations': len(asos_rows), 'asos_new_rows': a2,
                                     'highest_station': hi and {'name': hi['name'], 'ht_m': hi['ht_m'], 'ta': hi['ta'], 'td': hi['td'], 'hm': hi['hm'], 'ws10': hi['ws10']}}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
