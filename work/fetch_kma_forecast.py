"""Fetch the KMA 초단기예보 (6-hour very-short-range forecast) for every 5 km DFS grid point that covers
the Jeju 500 m cells, and write it for the dashboard.

Run with plain Python:  python work/fetch_kma_forecast.py
API Hub 예특보 > 단기예보 > 4. 동네예보 조회 (VilageFcstInfoService_2.0/getUltraSrtFcst). Issued hourly at
HH:30, available from about HH:45; base_time is the latest HH30 at least 45 minutes old. Each point
returns six forecast hours with RN1 (1 h rainfall text), PTY (precipitation type), T1H, SKY, WSD, REH, VEC, UUU, VVV.
Each point also carries elev_m: the mean DSM elevation of the 500 m cells mapped to it, used by the
dashboard as the point's representative height for the 6.5 degC/km lapse-rate correction.

DFS grid: Lambert conformal conic on a sphere (R=6371.00877 km, lat1=30, lat2=60, origin 126E/38N,
reference point X0=43, Y0=136 at 5 km). The conversion below is checked against nph-dfs_xy_lonlat
for three Jeju points before any forecast request; the run aborts on a mismatch.

Outputs
  runtime/kma/forecast/<base>.json                full response per point (never committed)
  runtime/kma/forecast/latest.json                compact document (also the shared-db body)
  outputs/jeju_dashboard/data/forecast.json       the same, for the static site / standalone build
"""
from pathlib import Path
import datetime as dt, json, math, re, sys, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT

KST = dt.timezone(dt.timedelta(hours=9))
BASE = 'https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/'
XY_API = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-dfs_xy_lonlat'
RE, GRID, SLAT1, SLAT2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136


def dfs_xy(lon, lat):
    d = math.pi / 180; re_ = RE / GRID; s1, s2, ol, oa = SLAT1 * d, SLAT2 * d, OLON * d, OLAT * d
    sn = math.tan(math.pi * .25 + s2 * .5) / math.tan(math.pi * .25 + s1 * .5); sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(sn)
    sf = math.tan(math.pi * .25 + s1 * .5); sf = sf ** sn * math.cos(s1) / sn
    ro = math.tan(math.pi * .25 + oa * .5); ro = re_ * sf / ro ** sn
    ra = math.tan(math.pi * .25 + lat * d * .5); ra = re_ * sf / ra ** sn
    th = lon * d - ol
    if th > math.pi: th -= 2 * math.pi
    if th < -math.pi: th += 2 * math.pi
    th *= sn
    # +1.5: the public KMA snippet adds XO/YO (0-based reference) and rounds to the 1-based grid number.
    return int(math.floor(ra * math.sin(th) + XO + 1.5)), int(math.floor(ro - ra * math.cos(th) + YO + 1.5))


def key_from_env():
    for line in (ROOT / '.env').read_text('utf-8-sig').splitlines():
        if line.strip().startswith('KMA_API_KEY='):
            return line.split('=', 1)[1].strip()
    return ''


def get(url, params, key, timeout=40):
    req = urllib.request.Request(url + '?' + urllib.parse.urlencode({**params, 'authKey': key}), headers={'User-Agent': 'Halla-GeoData/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def parse_rn1(text):
    """RN1 text -> mm (lower bound of a range; '1mm 미만' -> 0.5; '강수없음' -> 0)."""
    t = str(text).strip()
    if not t or t in ('강수없음', '-', '0'): return 0.0
    if '미만' in t: return 0.5
    m = re.findall(r'[\d.]+', t)
    return float(m[0]) if m else 0.0


def main():
    key = key_from_env()
    if not key:
        raise SystemExit('.env의 KMA_API_KEY가 비어 있습니다')
    grid = json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8'))
    points = {}
    for f in grid['features']:
        ring = f['geometry']['coordinates'][0]
        lon = sum(p[0] for p in ring[:-1]) / (len(ring) - 1); lat = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
        x, y = dfs_xy(lon, lat)
        points.setdefault(f'{x},{y}', {'nx': x, 'ny': y, 'cells': 0, 'lon': 0.0, 'lat': 0.0, 'elev': 0.0})
        pt = points[f'{x},{y}']; pt['cells'] += 1; pt['lon'] += lon; pt['lat'] += lat; pt['elev'] += float(f['properties'].get('elev_mean') or 0.0)
    for pt in points.values():
        pt['lon'] = round(pt['lon'] / pt['cells'], 5); pt['lat'] = round(pt['lat'] / pt['cells'], 5); pt['elev_m'] = round(pt['elev'] / pt['cells'], 1)
    # verify the conversion with the official converter on three points (summit, coast east, coast west)
    checks = []
    for lon, lat in [(126.5312, 33.3617), (126.9300, 33.4600), (126.1800, 33.3000)]:
        code, body = get(XY_API, {'lon': lon, 'lat': lat, 'help': '0'}, key)
        text = body.decode('utf-8', 'replace')
        nums = re.findall(r'-?\d+(?:\.\d+)?', text.split('\n')[-2] if '\n' in text.strip() else text)
        mine = dfs_xy(lon, lat)
        checks.append({'lon': lon, 'lat': lat, 'ours': mine, 'api_line': text.strip().splitlines()[-1][:80]})
        if f'{mine[0]}' not in text or f'{mine[1]}' not in text:
            raise SystemExit('DFS conversion mismatch: ' + json.dumps(checks[-1], ensure_ascii=False))
    print('DFS_CONVERSION_VERIFIED', json.dumps(checks, ensure_ascii=False), flush=True)

    now = dt.datetime.now(KST)
    base = (now - dt.timedelta(minutes=45)).replace(minute=30, second=0, microsecond=0)
    base_date, base_time = base.strftime('%Y%m%d'), base.strftime('%H%M')
    out_dir = ROOT / 'runtime/kma/forecast'; out_dir.mkdir(parents=True, exist_ok=True)
    raw_all = {}; forecast = {}; hours = set(); failures = []
    for k, pt in sorted(points.items()):
        try:
            code, body = get(BASE + 'getUltraSrtFcst', {'pageNo': 1, 'numOfRows': 1000, 'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time, 'nx': pt['nx'], 'ny': pt['ny']}, key)
            data = json.loads(body)
            items = data['response']['body']['items']['item']
        except Exception as e:
            failures.append({'point': k, 'error': type(e).__name__ + ': ' + str(e)[:120]}); continue
        raw_all[k] = items
        per_hour = {}
        for it in items:
            h = it['fcstDate'] + it['fcstTime']; hours.add(h)
            per_hour.setdefault(h, {})[it['category']] = it['fcstValue']
        forecast[k] = {'nx': pt['nx'], 'ny': pt['ny'], 'lon': pt['lon'], 'lat': pt['lat'], 'cells': pt['cells'], 'elev_m': pt['elev_m'],
                       'hours': {h: {'rn1_mm': parse_rn1(v.get('RN1', '')), 'rn1': v.get('RN1', ''), 'pty': v.get('PTY', ''), 't1h': v.get('T1H', ''), 'sky': v.get('SKY', ''), 'wsd': v.get('WSD', ''), 'reh': v.get('REH', ''), 'vec': v.get('VEC', ''), 'uuu': v.get('UUU', ''), 'vvv': v.get('VVV', '')} for h, v in sorted(per_hour.items())}}
        time.sleep(0.15)
    hours = sorted(hours)
    totals = {k: round(sum(h['rn1_mm'] for h in v['hours'].values()), 1) for k, v in forecast.items()}
    doc = {'schema_version': 1, 'source': 'KMA API Hub VilageFcstInfoService_2.0/getUltraSrtFcst (초단기예보)', 'base_time_kst': base.strftime('%Y-%m-%dT%H:%M:00+09:00'),
           'fetched_at': now.isoformat(), 'grid': 'DFS 5 km LCC (R=6371.00877 km, 30/60, 126E/38N, X0=43, Y0=136); verified with nph-dfs_xy_lonlat', 'hours': hours,
           'points': forecast, 'point_count': len(forecast), 'failed_points': failures,
           'summary': {'max_6h_total_mm': max(totals.values()) if totals else None, 'points_with_rain': sum(1 for t in totals.values() if t > 0),
                       'rn1_encoding': "RN1 text to mm: '강수없음'=0, '1mm 미만'=0.5, ranges use the lower bound", 'wind': 'VEC = direction the wind blows from, degrees clockwise from north; WSD m/s; UUU east and VVV north components m/s', 'elev_m': 'mean DSM elevation of the mapped 500 m cells (representative point height)', 'note': f'초단기예보 {base.strftime("%m-%d %H:%M")} KST 발표 · 이후 6시간 · 5 km 격자점 {len(forecast)}개'}}
    (out_dir / f'{base_date}{base_time}.json').write_text(json.dumps(raw_all, ensure_ascii=False), encoding='utf-8')
    text = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
    (out_dir / 'latest.json').write_text(text, encoding='utf-8')
    (ROOT / 'outputs/jeju_dashboard/data/forecast.json').write_text(text, encoding='utf-8')
    print('FORECAST_WRITTEN', json.dumps({'base': doc['base_time_kst'], 'points': len(forecast), 'failed': len(failures), 'hours': hours, **doc['summary']}, ensure_ascii=False), flush=True)
    return 0 if forecast else 2


if __name__ == '__main__':
    raise SystemExit(main())
