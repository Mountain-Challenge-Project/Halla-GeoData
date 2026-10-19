"""AWS hourly history for the Jeju stations from the KMA API Hub minute archive (official KMA observations, the same data
the 기상자료개방포털 CSV export carries; the API is used because the portal needs an interactive login).

nph-aws2_min accepts tm1/tm2 ranges (one day per request, ~1,440 rows per station). For every station, from START to
yesterday, the day is requested once and only the rows at minute :00 are kept as the hourly snapshot (the same convention as
the PR #17 collectors): TM, STN, TA, TD, HM, WS (WS10), WD (WD10), PA, PS, RN60 (RN-60m). Rows go to
runtime/kma/obs/aws_hourly/<YYYYMM>.csv (de-duplicated on TM+STN); progress is kept in
runtime/kma/obs/aws_hourly/_backfill_progress.json so the script can be stopped and resumed.

Order: stations by height (the mountain stations first), then the rest. Usage:
  python backfill_aws_hourly.py                 all stations, START..yesterday
  python backfill_aws_hourly.py --stations 871,870,868 --start 2023-01-01 --max-requests 3000
"""
import csv, json, sys, time, datetime as dt, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work'))
from fetch_kma_forecast import key_from_env, get, KST, ROOT  # noqa: E402

T = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min'
OUT = ROOT / 'runtime/kma/obs/aws_hourly'; PROG = OUT / '_backfill_progress.json'
COLS = ['TM', 'STN', 'TA', 'TD', 'HM', 'WS', 'WD', 'PA', 'PS', 'RN60']
AWS_IDX = {'TM': 0, 'STN': 1, 'WD1': 2, 'WS1': 3, 'WDS': 4, 'WSS': 5, 'WD10': 6, 'WS10': 7, 'TA': 8, 'RE': 9, 'RN15': 10, 'RN60': 11, 'RN12H': 12, 'RNDAY': 13, 'HM': 14, 'PA': 15, 'PS': 16, 'TD': 17}
GDA = Path(__file__).resolve().parents[1]


def clean(v):
    try: return '' if float(v) <= -9 and v.startswith('-9') else v
    except ValueError: return ''


def fetch_day(stn, day, key, tries=4):
    t1 = day.strftime('%Y%m%d0000'); t2 = day.strftime('%Y%m%d2359')
    for i in range(tries):
        try:
            code, body = get(T, {'tm1': t1, 'tm2': t2, 'stn': stn, 'disp': '0', 'help': '0'}, key, 180)
            text = body.decode('utf-8', 'replace'); rows = []
            for line in text.splitlines():
                if not line or line.startswith('#'): continue
                p = line.split()
                if len(p) < 18 or p[1] != stn or not p[0].endswith('00'): continue
                rows.append({'TM': p[0], 'STN': stn, 'TA': clean(p[8]), 'TD': clean(p[17]), 'HM': clean(p[14]), 'WS': clean(p[7]), 'WD': clean(p[6]), 'PA': clean(p[15]), 'PS': clean(p[16]), 'RN60': clean(p[11])})
            return rows, len(text)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403): raise
            time.sleep(5 * (i + 1))
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(5 * (i + 1))
    return None, 0


def run_station(s, start, end, max_req, key, seen, prog, lock, counters):
    stn = s['stn']; done_until = dt.date.fromisoformat(prog[stn]) if stn in prog else start - dt.timedelta(days=1)
    day = max(start, done_until + dt.timedelta(days=1))
    while day <= end and counters['req'] < max_req:
        rows, nbytes = fetch_day(stn, day, key)
        with lock: counters['req'] += 1
        if rows is None:
            print(f'  {stn} {day}: failed, will retry next run', flush=True); return
        month = day.strftime('%Y%m'); path = OUT / f'{month}.csv'
        with lock:
            new = not path.exists()
            with path.open('a', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=COLS)
                if new: w.writeheader()
                for r in rows:
                    if (r['TM'], stn) in seen.setdefault(month, set()): continue
                    w.writerow(r); seen[month].add((r['TM'], stn)); counters['rows'] += 1
            prog[stn] = day.isoformat(); PROG.write_text(json.dumps(prog, indent=1), encoding='utf-8')
            if counters['req'] % 50 == 0: print(f'  {counters["req"]} requests, {counters["rows"]} hourly rows; {s["name"]} at {day}', flush=True)
        day += dt.timedelta(days=1); time.sleep(0.25)


def main(argv):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    key = key_from_env()
    if not key: raise SystemExit('.env의 KMA_API_KEY가 비어 있습니다')
    args = dict(zip(argv[::2], argv[1::2]))
    start = dt.date.fromisoformat(args.get('--start', '2023-01-01')); end = dt.date.today() - dt.timedelta(days=1); max_req = int(args.get('--max-requests', '1000000')); workers = int(args.get('--workers', '4'))
    with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f: stations = sorted(csv.DictReader(f), key=lambda r: -(float(r['ht_m'] or 0)))
    only = set(args['--stations'].split(',')) if '--stations' in args else None
    stations = [s for s in stations if not only or s['stn'] in only]
    OUT.mkdir(parents=True, exist_ok=True); prog = json.loads(PROG.read_text('utf-8')) if PROG.exists() else {}
    seen = {}
    for p in OUT.glob('2*.csv'):
        with p.open(encoding='utf-8') as f:
            for r in csv.DictReader(f): seen.setdefault(p.stem, set()).add((r['TM'], r['STN']))
    lock = threading.Lock(); counters = {'req': 0, 'rows': 0}; t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda s: run_station(s, start, end, max_req, key, seen, prog, lock, counters), stations))
    print('AWS_BACKFILL', json.dumps({'requests': counters['req'], 'hourly_rows_added': counters['rows'], 'seconds': round(time.time() - t0), 'progress': prog}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1:])
