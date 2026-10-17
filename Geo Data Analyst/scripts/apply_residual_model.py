"""Stage 4c: apply the trained residual models to every cell for the current forecast hour (anaconda Python).

Reads runtime/kma/models/residual_{t,td}.joblib (written by train_residual_model.py only when the archive is
large enough) and the same inputs as compute_stage2.py, builds the feature vector of each cell (station height =
cell mean elevation) and writes outputs/jeju_dashboard/data/ml_cells.json:
  {status, hour, issue_kst, model:{t:name, td:name}, trained_rows, cells:{grid_id:[t_corrected, td_corrected]}}
When no model exists the file carries status 'no_model' and the dashboard keeps the option disabled.
"""
import json, math, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / 'work'))
import compute_stage2 as cs  # noqa: E402
from physics_modules import dir_index  # noqa: E402
ROOT = cs.ROOT; MODELS = ROOT / 'runtime/kma/models'; OUT = ROOT / 'outputs/jeju_dashboard/data/ml_cells.json'


def main():
    fc, grid, levels = cs.fc, cs.grid, cs.levels; hour = fc['hours'][0]
    found = {k: MODELS / f'residual_{k}.joblib' for k in ('t', 'td')}
    if not all(p.exists() for p in found.values()):
        OUT.write_text(json.dumps({'status': 'no_model', 'hour': hour, 'issue_kst': fc['base_time_kst'], 'message': 'residual models not trained yet (feature archive below the thresholds)'}, ensure_ascii=False), encoding='utf-8')
        print('ML_CELLS', 'no_model'); return
    import joblib; m = {k: joblib.load(p) for k, p in found.items()}; feats = m['t']['features']
    dtm = __import__('datetime').datetime.strptime(hour, '%Y%m%d%H%M'); doy = dtm.timetuple().tm_yday
    rows = []; ids = []
    for f in grid['features']:
        p = f['properties']; lon, lat = cs.centre(f); key, pt = cs.point_for(lon, lat)
        if not pt or hour not in pt['hours']: continue
        h = pt['hours'][hour]; st = cs.cell_physics(p, lon, lat, hour)
        if not st: continue
        L = (levels and levels['points'].get(key, {}).get(hour)) or {}; w = cs.cross_wind(key, hour, h); i = dir_index(w[0]) if w else None
        vec = cs.num if False else None
        try: vec = float(h.get('vec'))
        except (TypeError, ValueError): vec = None
        asp = p.get('asp_deg'); fo = st.get('foehn'); ze = p.get('elev_mean') or 0
        v = {'hour_kst': int(hour[8:10]), 'doy_sin': math.sin(2 * math.pi * doy / 365.25), 'doy_cos': math.cos(2 * math.pi * doy / 365.25), 'stn_ht_m': ze, 'cell_elev_m': ze, 'pt_elev_m': pt.get('elev_m'), 'dz_cell_pt': ze - (pt.get('elev_m') or 0),
             'mean_deg': p.get('mean_deg'), 'asp_sin': math.sin(math.radians(asp)) if asp is not None else np.nan, 'asp_cos': math.cos(math.radians(asp)) if asp is not None else np.nan, 'asp_r': p.get('asp_r', np.nan),
             'tpi_1km_m': p.get('tpi_1km_m'), 'svf': p.get('svf'), 'coast_km': p.get('coast_km'), 'lc_tree': p.get('lc_tree', np.nan), 'lc_grass': p.get('lc_grass', np.nan), 'lc_crop': p.get('lc_crop', np.nan), 'lc_builtup': p.get('lc_builtup', np.nan), 'lc_water': p.get('lc_water', np.nan), 'canopy_mean_m': p.get('canopy_mean_m', np.nan), 'ridge_m': p['up_max'][i] if (i is not None and p.get('up_max')) else np.nan, 'lee_m': (p['up_max'][i] - ze) if (i is not None and p.get('up_max')) else np.nan,
             't1h': float(h['t1h']), 'reh': float(h['reh']), 'wsd': float(h['wsd']), 'vec_sin': math.sin(math.radians(vec)) if vec is not None else np.nan, 'vec_cos': math.cos(math.radians(vec)) if vec is not None else np.nan,
             'rn1_mm': h.get('rn1_mm'), 'sky': float(h.get('sky') or np.nan), 'pty': float(h.get('pty') or np.nan), 't850': L.get('t850', np.nan), 'rh850': L.get('rh850', np.nan), 'u850': L.get('u850', np.nan), 'v850': L.get('v850', np.nan),
             't925': L.get('t925', np.nan), 'rh925': L.get('rh925', np.nan), 'u925': L.get('u925', np.nan), 'v925': L.get('v925', np.nan), 'lapse_t': st['t'], 'lapse_td': st['td'], 'lcl_rel_m': st['lcl_rel'],
             'foehn_index': fo['index'] if fo else np.nan, 'foehn_active': int(bool(fo and fo['active']))}
        rows.append([float(v[k]) if v[k] is not None and v[k] != '' else np.nan for k in feats]); ids.append((p['grid_id'], st['t'], st['td']))
    X = np.array(rows, float); rt = m['t']['model'].predict(X); rtd = m['td']['model'].predict(X)
    cells = {g: [round(t + a, 1), round(min(td + b, t + a), 1)] for (g, t, td), a, b in zip(ids, rt, rtd)}
    doc = {'status': 'ok', 'hour': hour, 'issue_kst': fc['base_time_kst'], 'model': {k: m[k]['name'] for k in m}, 'trained_rows': m['t']['rows'], 'trained_at': m['t']['trained_at'], 'cells': cells,
           'note': 'physics estimate + learned residual (obs - physics) from the station archive; leave-one-station-out error in residual_model_report.json'}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('ML_CELLS', json.dumps({'status': 'ok', 'cells': len(cells), 'hour': hour, 'model': doc['model']}))


if __name__ == '__main__':
    main()
