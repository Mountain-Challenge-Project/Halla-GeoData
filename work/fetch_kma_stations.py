"""Stage 1a: KMA station metadata for Jeju, mapped to the 500 m radar cells.

Reads the API Hub station lists (지상관측 지점정보: inf=AWS and inf=SFC), keeps the stations inside the Jeju
bounding box, finds the dashboard cell (outputs/jeju_dashboard/data/grid.geojson) that contains each station
by point-in-polygon, and writes

  inputs/reference/kma_stations_jeju.csv       one row per station (both lists merged; ASOS rows carry kind=SFC)
  inputs/reference/kma_stations_jeju.geojson   the same as points, for QGIS / the dashboard
  work/public_sources/kma_stn_inf_{AWS,SFC}.txt the raw responses (key removed)

Run with the system Python (needs .env with KMA_API_KEY). The station height HT is the enclosure
elevation reported by KMA; the cell's mean DSM elevation is attached as cell_elev_m for lapse-rate work.
"""
import csv, json, sys, datetime as dt, time, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_kma_forecast import key_from_env, get, KST, ROOT  # noqa: E402

T = 'https://apihub.kma.go.kr/api/typ01/url/stn_inf.php'
BBOX = (126.05, 33.05, 127.05, 33.65)   # lon_min, lat_min, lon_max, lat_max (includes 마라도·우도·추자 제외)
AWS_COLS = ['STN', 'LON', 'LAT', 'STN_SP', 'HT', 'HT_WD', 'LAU_ID', 'STN_AD', 'STN_KO', 'STN_EN', 'FCT_ID', 'LAW_ID', 'BASIN']
SFC_COLS = ['STN', 'LON', 'LAT', 'STN_SP', 'HT', 'HT_PA', 'HT_TA', 'HT_WD', 'HT_RN', 'STN_AD', 'STN_KO', 'STN_EN', 'FCT_ID', 'LAW_ID', 'BASIN']


def decode(raw):
    try: return raw.decode('utf-8')
    except UnicodeDecodeError: return raw.decode('cp949', 'replace')


def fetch(inf, key, tries=4):
    for i in range(tries):
        try:
            code, body = get(T, {'inf': inf, 'stn': '0', 'tm': dt.datetime.now(KST).strftime('%Y%m%d%H%M'), 'help': '0'}, key, 120)
            return decode(body)
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504) and i < tries - 1: time.sleep(5); continue
            raise


def parse(text, cols):
    out = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'): continue
        parts = line.split(None, len(cols))          # the last column (LAW_ADDR) may contain spaces
        if len(parts) < len(cols): continue
        rec = dict(zip(cols, parts[:len(cols)])); rec['LAW_ADDR'] = parts[len(cols)].strip() if len(parts) > len(cols) else ''
        out.append(rec)
    return out


def point_in_ring(x, y, ring):
    inside = False; n = len(ring)
    for i in range(n - 1):
        x1, y1 = ring[i]; x2, y2 = ring[i + 1]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x: inside = not inside
    return inside


def main():
    key = key_from_env()
    if not key: raise SystemExit('.env의 KMA_API_KEY가 비어 있습니다')
    grid = json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8'))
    cells = []
    for f in grid['features']:
        ring = f['geometry']['coordinates'][0]; xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        cells.append((min(xs), min(ys), max(xs), max(ys), ring, f['properties']))
    stations = {}
    for inf, cols in [('AWS', AWS_COLS), ('SFC', SFC_COLS)]:
        text = fetch(inf, key)
        (ROOT / 'work/public_sources' / f'kma_stn_inf_{inf}.txt').write_text(text.replace(key, '<KEY>'), encoding='utf-8')
        n = 0
        for r in parse(text, cols):
            try: lon, lat = float(r['LON']), float(r['LAT'])
            except ValueError: continue
            if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]): continue
            rec = stations.setdefault(r['STN'], {'stn': int(r['STN']), 'name': r['STN_KO'], 'name_en': r['STN_EN'], 'lon': lon, 'lat': lat,
                                                 'ht_m': float(r['HT']) if r['HT'] not in ('', '-') else None, 'kinds': []})
            rec['kinds'].append(inf); n += 1
            if inf == 'SFC':
                rec['name'] = r['STN_KO']; rec['ht_pa_m'] = float(r['HT_PA']); rec['ht_wd_m'] = float(r['HT_WD'])
            else:
                rec['ht_wd_m'] = rec.get('ht_wd_m') or (float(r['HT_WD']) if r['HT_WD'] not in ('', '-') else None)
            rec['law_addr'] = r.get('LAW_ADDR', '')
        print(f'{inf}: {n} stations inside the Jeju box')
    mapped = 0
    for rec in stations.values():
        rec['grid_id'] = None; rec['cell_elev_m'] = None
        for (x0, y0, x1, y1, ring, p) in cells:
            if x0 <= rec['lon'] <= x1 and y0 <= rec['lat'] <= y1 and point_in_ring(rec['lon'], rec['lat'], ring):
                rec['grid_id'] = p['grid_id']; rec['cell_elev_m'] = round(p['elev_mean'], 1); rec['cell_mean_slope_deg'] = round(p['mean_deg'], 2); mapped += 1; break
        rec['kind'] = 'SFC' if 'SFC' in rec['kinds'] else 'AWS'; del rec['kinds']
    rows = sorted(stations.values(), key=lambda r: r['stn'])
    out_csv = ROOT / 'inputs/reference/kma_stations_jeju.csv'
    with out_csv.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['stn', 'kind', 'name', 'name_en', 'lon', 'lat', 'ht_m', 'ht_pa_m', 'ht_wd_m', 'grid_id', 'cell_elev_m', 'cell_mean_slope_deg', 'law_addr'])
        w.writeheader(); [w.writerow({k: r.get(k) for k in w.fieldnames}) for r in rows]
    gj = {'type': 'FeatureCollection', 'source': 'KMA API Hub 지상관측 지점정보 (stn_inf.php inf=AWS, inf=SFC)', 'fetched_at': dt.datetime.now(KST).isoformat(),
          'features': [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['lon'], r['lat']]}, 'properties': {k: v for k, v in r.items() if k not in ('lon', 'lat')}} for r in rows]}
    (ROOT / 'inputs/reference/kma_stations_jeju.geojson').write_text(json.dumps(gj, ensure_ascii=False, indent=1), encoding='utf-8')
    unmapped = [r['name'] for r in rows if not r['grid_id']]
    print('STATIONS_WRITTEN', json.dumps({'total': len(rows), 'asos': sum(1 for r in rows if r['kind'] == 'SFC'), 'mapped_to_cells': mapped, 'unmapped': unmapped,
                                          'highest': max(rows, key=lambda r: r['ht_m'] or 0)['name']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
