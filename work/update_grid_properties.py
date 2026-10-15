"""Join cell aspect (asp_deg, asp_r) and the static terrain factors into the dashboard grid.

Sources: outputs/jeju_slope/jeju_grid_slope.csv (asp_deg, asp_r) and, when present,
Geo Data Analyst/data/jeju_grid_terrain_factors.csv from Geo Data Analyst/scripts/build_terrain_factors.py (tpi_1km_m, svf, coast_km and the
16-direction upstream ridge height/distance, packed as up_max / up_dist lists ordered N, NNE, ... NNW).

outputs/jeju_dashboard/data/grid.geojson keeps a small property set for the browser. The wind-exposure
metric needs the area-weighted circular mean aspect (asp_deg, degrees clockwise from north, downhill
direction) and its concentration (asp_r, 0-1). Run after build_slope_data.py / the dashboard grid rebuild.
"""
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
csv_path = ROOT / 'outputs/jeju_slope/jeju_grid_slope.csv'
geo_path = ROOT / 'outputs/jeju_dashboard/data/grid.geojson'
rows = {r['grid_id']: r for r in csv.DictReader(csv_path.open(encoding='utf-8-sig'))}
g = json.loads(geo_path.read_text('utf-8'))
n = 0
for f in g['features']:
    p = f['properties']; r = rows.get(p['grid_id'])
    if not r: continue
    if r['asp_deg'] in ('', None) or r['asp_r'] in ('', None):
        p['asp_deg'] = None; p['asp_r'] = None; continue   # flat cell: no aspect
    p['asp_deg'] = round(float(r['asp_deg']), 1); p['asp_r'] = round(float(r['asp_r']), 3); n += 1
tf_path = ROOT / 'Geo Data Analyst/data/jeju_grid_terrain_factors.csv'
DIRS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
m = 0
if tf_path.exists():
    tf = {r['grid_id']: r for r in csv.DictReader(tf_path.open(encoding='utf-8'))}
    for f in g['features']:
        p = f['properties']; r = tf.get(p['grid_id'])
        if not r: continue
        p['tpi_1km_m'] = float(r['tpi_1km_m']); p['svf'] = float(r['svf']); p['coast_km'] = float(r['coast_km'])
        p['up_max'] = [int(float(r[f'up_max_{d}'])) for d in DIRS]; p['up_dist'] = [float(r[f'up_dist_{d}']) for d in DIRS]; m += 1
geo_path.write_text(json.dumps(g, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print('GRID_ASPECT_JOINED', n, 'of', len(g['features']), '| terrain factors joined', m, '|', geo_path.stat().st_size, 'bytes')
