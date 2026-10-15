"""Join cell aspect (asp_deg, asp_r) from outputs/jeju_slope/jeju_grid_slope.csv into the dashboard grid.

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
geo_path.write_text(json.dumps(g, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print('GRID_ASPECT_JOINED', n, 'of', len(g['features']), geo_path.stat().st_size, 'bytes')
