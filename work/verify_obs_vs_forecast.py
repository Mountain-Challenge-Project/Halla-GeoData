"""Stage 1 sanity check: the lapse-corrected cell temperature (physics module, no learning) against the
AWS observations at the same minute. Prints bias/RMSE for the raw 5 km point value and for the corrected value.

Inputs: outputs/jeju_dashboard/data/obs_latest.json (work/fetch_kma_obs.py), forecast.json (work/fetch_kma_forecast.py),
grid.geojson (cell elevation). Writes outputs/jeju_slope/obs_vs_forecast_check.json. Not a model validation:
one forecast issue, one minute of observations, the forecast hour nearest the observation time.
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_kma_forecast import dfs_xy, ROOT  # noqa: E402

obs = json.loads((ROOT / 'outputs/jeju_dashboard/data/obs_latest.json').read_text('utf-8'))
fc = json.loads((ROOT / 'outputs/jeju_dashboard/data/forecast.json').read_text('utf-8'))
grid = {f['properties']['grid_id']: f['properties'] for f in json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8'))['features']}

def magnus_td(t, rh):
    a, b = 17.62, 243.12; g = math.log(max(rh, 1) / 100) + a * t / (b + t); return b * g / (a - g)

rows = []
for stn, st in obs['stations'].items():
    if not st.get('grid_id') or st.get('ta') in (None, ''): continue
    cell = grid[st['grid_id']]; x, y = dfs_xy(st['lon'], st['lat']); pt = fc['points'].get(f'{x},{y}')
    if not pt: continue
    tm = st['tm']; hour = min(fc['hours'], key=lambda h: abs(int(h[8:10]) - (int(tm[8:10]) + (1 if int(tm[10:12]) >= 30 else 0))))
    v = pt['hours'].get(hour)
    if not v: continue
    t0 = float(v['t1h']); rh0 = float(v['reh']); ta = float(st['ta'])
    t_cell = t0 - 0.0065 * (cell['elev_mean'] - pt['elev_m'])
    t_stn = t0 - 0.0065 * ((st.get('ht_m') or cell['elev_mean']) - pt['elev_m'])   # same correction to the station's own height
    td0 = magnus_td(t0, rh0); td_cell = td0 - 0.002 * (cell['elev_mean'] - pt['elev_m'])
    rows.append({'stn': stn, 'name': st['name'], 'ht_m': st.get('ht_m'), 'cell_elev_m': cell['elev_mean'], 'point': f'{x},{y}', 'point_elev_m': pt['elev_m'], 'hour': hour,
                 'obs_ta': ta, 'obs_td': float(st['td']) if st.get('td') not in (None, '') else None, 'raw_t1h': t0, 'cell_t': round(t_cell, 1), 'stn_t': round(t_stn, 1), 'cell_td': round(td_cell, 1)})

def stats(key):
    e = [r[key] - r['obs_ta'] for r in rows]; return {'n': len(e), 'bias': round(sum(e) / len(e), 2), 'rmse': round(math.sqrt(sum(x * x for x in e) / len(e)), 2), 'max_abs': round(max(abs(x) for x in e), 2)}
def stats_td():
    e = [r['cell_td'] - r['obs_td'] for r in rows if r['obs_td'] is not None]; return {'n': len(e), 'bias': round(sum(e) / len(e), 2), 'rmse': round(math.sqrt(sum(x * x for x in e) / len(e)), 2)}
hi = [r for r in rows if (r['ht_m'] or 0) >= 700]
def stats_sub(rs, key):
    e = [r[key] - r['obs_ta'] for r in rs]; return {'n': len(e), 'bias': round(sum(e) / len(e), 2), 'rmse': round(math.sqrt(sum(x * x for x in e) / len(e)), 2)} if e else None
out = {'obs_time': obs['fetched_at'], 'forecast_base_kst': fc['base_time_kst'], 'stations': len(rows),
       'temperature': {'raw_5km_point': stats('raw_t1h'), 'cell_lapse_corrected': stats('cell_t'), 'station_height_corrected': stats('stn_t')},
       'temperature_stations_above_700m': {'raw_5km_point': stats_sub(hi, 'raw_t1h'), 'station_height_corrected': stats_sub(hi, 'stn_t')},
       'dew_point_cell_vs_obs': stats_td(), 'rows': rows,
       'note': 'single issue / single minute; physics only (6.5 and 2 degC/km lapse), no learned residual; forecast hour nearest the observation'}
(ROOT / 'outputs/jeju_slope/obs_vs_forecast_check.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print('OBS_VS_FORECAST', json.dumps({k: v for k, v in out.items() if k != 'rows'}, ensure_ascii=False))
for r in sorted(rows, key=lambda r: -(r['ht_m'] or 0))[:6]: print(' ', r['name'], r['ht_m'], 'obs', r['obs_ta'], 'raw', r['raw_t1h'], 'stn_corr', r['stn_t'], 'cell', r['cell_t'])
