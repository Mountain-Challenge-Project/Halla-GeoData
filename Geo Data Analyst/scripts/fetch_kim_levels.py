"""Stage 2a: KIM local model (KIM-L, 1.5 km) pressure-level fields for Jeju, aggregated to the 5 km DFS points.

API Hub 수치모델 > 수치예보모델 > nwp_nc_prs2d_down.php (group=KIML, approved). For the newest issue (00/06/12/18 UTC)
and lead hours 0..HF_MAX, the fields T (K), RH (%), U, V (m/s) at 925 and 850 hPa are read for the Jeju box as CSV
(ix,iy,lon,lat,value; 4,565 points) and averaged over the KIM points that fall in each DFS 5 km cell, keyed like
forecast.json ("x,y"). This gives the upstream air state for the foehn module and the cross-barrier wind.

Outputs
  runtime/kma/kim/<tmfc>_<var>_<lvl>_hf<h>.csv   raw responses (local only)
  outputs/jeju_dashboard/data/levels.json          {tmfc_utc, hours (KST, YYYYMMDDHH00), levels, points:{"x,y":{hour:{t850,rh850,u850,v850,t925,...}}}}
Temperatures are converted to degC. Run with the system Python (.env KMA_API_KEY).
"""
import sys, json, time, datetime as dt, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work'))
from fetch_kma_forecast import key_from_env, get, dfs_xy, KST, ROOT  # noqa: E402

API = 'https://apihub.kma.go.kr/api/typ06/url/nwp_nc_prs2d_down.php'
BOX = {'lon1': 126.1, 'lat1': 33.1, 'lon2': 127.0, 'lat2': 33.6, 'dataType': 'CSV', 'group': 'KIML'}
LEVELS = ['925', '850']; VARS = ['T', 'RH', 'U', 'V']; HF_MAX = 9
RAW = ROOT / 'runtime/kma/kim'


def fetch(params, key, tries=4):
    for i in range(tries):
        try:
            code, body = get(API, params, key, 120); text = body.decode('utf-8', 'replace')
            if text.startswith('# ERROR') or 'ix,iy' not in text[:40]: raise RuntimeError(text[:120])
            return text
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, RuntimeError) as e:
            if i < tries - 1: time.sleep(5 * (i + 1)); continue
            raise


def latest_issue(key):
    """newest 6-hourly issue whose hf=0 850 hPa T exists (the API serves a run ~3-4 h after its base time)."""
    utc = dt.datetime.now(dt.timezone.utc)
    for back in range(0, 4):
        t = utc - dt.timedelta(hours=6 * back); tmfc = t.strftime('%Y%m%d') + '%02d' % (t.hour // 6 * 6)
        try:
            fetch({**BOX, 'vars': 'T', 'lvl_lst': '850', 'tmfc': tmfc, 'hf': '0'}, key, tries=1); return tmfc
        except Exception: continue
    raise SystemExit('no KIM issue available in the last 24 h')


def main():
    key = key_from_env()
    if not key: raise SystemExit('.env의 KMA_API_KEY가 비어 있습니다')
    tmfc = latest_issue(key); RAW.mkdir(parents=True, exist_ok=True)
    base = dt.datetime.strptime(tmfc, '%Y%m%d%H').replace(tzinfo=dt.timezone.utc)
    keymap = None; points = {}; hours = []
    for hf in range(0, HF_MAX + 1):
        hour_kst = (base + dt.timedelta(hours=hf)).astimezone(KST).strftime('%Y%m%d%H00'); hours.append(hour_kst)
        for lvl in LEVELS:
            for var in VARS:
                text = fetch({**BOX, 'vars': var, 'lvl_lst': lvl, 'tmfc': tmfc, 'hf': str(hf)}, key)
                (RAW / f'{tmfc}_{var}_{lvl}_hf{hf}.csv').write_text(text, encoding='utf-8')
                rows = [l.split(',') for l in text.splitlines() if l and not l.startswith('ix')]
                if keymap is None:
                    keymap = {}
                    for r in rows:
                        x, y = dfs_xy(float(r[2]), float(r[3])); keymap[(r[0], r[1])] = f'{x},{y}'
                acc = {}
                for r in rows:
                    k = keymap[(r[0], r[1])]; v = float(r[4]); a = acc.setdefault(k, [0.0, 0]); a[0] += v; a[1] += 1
                name = f'{var.lower()}{lvl}'
                for k, (s, n) in acc.items():
                    v = s / n
                    if var == 'T': v -= 273.15
                    points.setdefault(k, {}).setdefault(hour_kst, {})[name] = round(v, 2)
        print(f'  hf{hf} {hour_kst} KST done', flush=True); time.sleep(0.3)
    doc = {'schema_version': 1, 'source': 'KMA API Hub KIM-L (group=KIML) nwp_nc_prs2d_down, 1.5 km points averaged per DFS 5 km cell',
           'tmfc_utc': tmfc, 'fetched_at': dt.datetime.now(KST).isoformat(), 'hours': hours, 'levels_hPa': [int(l) for l in LEVELS], 'vars': 'T degC, RH %, U east m/s, V north m/s',
           'point_count': len(points), 'kim_points_in_box': len(keymap), 'points': points}
    text = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
    (ROOT / 'outputs/jeju_dashboard/data/levels.json').write_text(text, encoding='utf-8'); (RAW / 'latest.json').write_text(text, encoding='utf-8')
    k54 = points.get('54,36', {}).get(hours[0], {})
    print('LEVELS_WRITTEN', json.dumps({'tmfc_utc': tmfc, 'hours': [hours[0], hours[-1]], 'dfs_points': len(points), 'summit_point_h0': k54}, ensure_ascii=False))


if __name__ == '__main__':
    main()
