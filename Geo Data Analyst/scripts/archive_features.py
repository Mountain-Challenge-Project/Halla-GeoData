"""Stage 4a: feature archive for the residual-learning model (one row per station per forecast issue).

Run after compute_stage2.py (RUN_PIPELINE.cmd does). For every mapped station it records the full input vector
the model will learn from and the observation targets:
  keys      issue_kst, hour, stn, grid_id
  time      hour_kst, month, doy_sin, doy_cos
  terrain   stn_ht_m, cell_elev_m, pt_elev_m, dz_cell_pt, mean_deg, asp_sin, asp_cos, asp_r, tpi_1km_m, svf, coast_km, ridge_m, lee_m
  surface   lc_tree, lc_grass, lc_crop, lc_builtup, lc_water (ESA WorldCover shares %), canopy_mean_m (ETH canopy height)
  forecast  t1h, reh, wsd, vec_sin, vec_cos, rn1_mm, sky, pty
  kim       t850, rh850, u850, v850, t925, rh925, u925, v925   (NaN when levels.json has no value for the hour)
  physics   lapse_t, lapse_td, lcl_rel_m, foehn_index, foehn_active, foehn_t, foehn_td
  targets   obs_ta, obs_td, obs_hm, obs_ws10, obs_tm
Appended to runtime/kma/verification/features.csv (local). The residual the model learns is obs - physics.
"""
import csv, json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / 'work'))
import compute_stage2 as cs  # noqa: E402  (loads forecast/levels/obs/grid at import)
from physics_modules import dir_index  # noqa: E402
ROOT = cs.ROOT; GDA = HERE.parent
OUT = ROOT / 'runtime/kma/verification/features.csv'
COLS = ['issue_kst', 'hour', 'stn', 'name', 'grid_id', 'hour_kst', 'month', 'doy_sin', 'doy_cos', 'stn_ht_m', 'cell_elev_m', 'pt_elev_m', 'dz_cell_pt', 'mean_deg', 'asp_sin', 'asp_cos', 'asp_r',
        'tpi_1km_m', 'svf', 'coast_km', 'ridge_m', 'lee_m', 'lc_tree', 'lc_grass', 'lc_crop', 'lc_builtup', 'lc_water', 'canopy_mean_m', 't1h', 'reh', 'wsd', 'vec_sin', 'vec_cos', 'rn1_mm', 'sky', 'pty', 't850', 'rh850', 'u850', 'v850', 't925', 'rh925', 'u925', 'v925',
        'lapse_t', 'lapse_td', 'lcl_rel_m', 'foehn_index', 'foehn_active', 'foehn_t', 'foehn_td', 'obs_ta', 'obs_td', 'obs_hm', 'obs_ws10', 'obs_tm']


def num(v):
    try:
        x = float(v); return x
    except (TypeError, ValueError): return None


def main():
    fc, grid, levels, obs = cs.fc, cs.grid, cs.levels, cs.obs
    if not obs: raise SystemExit('obs_latest.json missing')
    hour = fc['hours'][0]; issue = fc['base_time_kst']
    feats = {f['properties']['grid_id']: f for f in grid['features']}
    with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f: stations = {r['stn']: r for r in csv.DictReader(f)}
    OUT.parent.mkdir(parents=True, exist_ok=True); new = not OUT.exists(); seen = set()
    if not new:
        with OUT.open(encoding='utf-8') as f:
            rd = csv.DictReader(f); old_rows = list(rd); old_cols = rd.fieldnames or []
        for r in old_rows: seen.add((r['issue_kst'], r['stn']))
        if old_cols != COLS:   # the feature set grew: rewrite the archive with the current columns so every row stays aligned
            with OUT.open('w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); [w.writerow({c: r.get(c, '') for c in COLS}) for r in old_rows]
    dt = __import__('datetime').datetime.strptime(hour, '%Y%m%d%H%M'); doy = dt.timetuple().tm_yday
    added = 0
    with OUT.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new: w.writeheader()
        for stn, s in obs['stations'].items():
            if (issue, stn) in seen or not s.get('grid_id') or s['grid_id'] not in feats: continue
            fe = feats[s['grid_id']]; p = fe['properties']; lon, lat = cs.centre(fe); key, pt = cs.point_for(lon, lat)
            if not pt or hour not in pt['hours']: continue
            h = pt['hours'][hour]; st = cs.cell_physics(p, lon, lat, hour)
            if not st: continue
            L = (levels and levels['points'].get(key, {}).get(hour)) or {}
            w_ = cs.cross_wind(key, hour, h); i = dir_index(w_[0]) if w_ else None
            vec = num(h.get('vec')); asp = p.get('asp_deg'); fo = st.get('foehn')
            row = {'issue_kst': issue, 'hour': hour, 'stn': stn, 'name': s['name'], 'grid_id': s['grid_id'], 'hour_kst': int(hour[8:10]), 'month': int(hour[4:6]),
                   'doy_sin': round(math.sin(2 * math.pi * doy / 365.25), 4), 'doy_cos': round(math.cos(2 * math.pi * doy / 365.25), 4),
                   'stn_ht_m': s.get('ht_m'), 'cell_elev_m': round(p.get('elev_mean') or 0, 1), 'pt_elev_m': pt.get('elev_m'), 'dz_cell_pt': round((p.get('elev_mean') or 0) - (pt.get('elev_m') or 0), 1),
                   'mean_deg': p.get('mean_deg'), 'asp_sin': round(math.sin(math.radians(asp)), 4) if asp is not None else '', 'asp_cos': round(math.cos(math.radians(asp)), 4) if asp is not None else '', 'asp_r': p.get('asp_r', ''),
                   'tpi_1km_m': p.get('tpi_1km_m'), 'svf': p.get('svf'), 'coast_km': p.get('coast_km'), 'lc_tree': p.get('lc_tree', ''), 'lc_grass': p.get('lc_grass', ''), 'lc_crop': p.get('lc_crop', ''), 'lc_builtup': p.get('lc_builtup', ''), 'lc_water': p.get('lc_water', ''), 'canopy_mean_m': p.get('canopy_mean_m', ''), 'ridge_m': p['up_max'][i] if (i is not None and p.get('up_max')) else '', 'lee_m': (p['up_max'][i] - (p.get('elev_mean') or 0)) if (i is not None and p.get('up_max')) else '',
                   't1h': num(h.get('t1h')), 'reh': num(h.get('reh')), 'wsd': num(h.get('wsd')), 'vec_sin': round(math.sin(math.radians(vec)), 4) if vec is not None else '', 'vec_cos': round(math.cos(math.radians(vec)), 4) if vec is not None else '',
                   'rn1_mm': h.get('rn1_mm'), 'sky': h.get('sky'), 'pty': h.get('pty'),
                   't850': L.get('t850', ''), 'rh850': L.get('rh850', ''), 'u850': L.get('u850', ''), 'v850': L.get('v850', ''), 't925': L.get('t925', ''), 'rh925': L.get('rh925', ''), 'u925': L.get('u925', ''), 'v925': L.get('v925', ''),
                   'lapse_t': round(st['t'], 2), 'lapse_td': round(st['td'], 2), 'lcl_rel_m': round(st['lcl_rel']), 'foehn_index': round(fo['index'], 2) if fo else '', 'foehn_active': int(bool(fo and fo['active'])),
                   'foehn_t': round(fo['t'], 2) if fo else '', 'foehn_td': round(fo['td'], 2) if fo else '',
                   'obs_ta': s.get('ta'), 'obs_td': s.get('td'), 'obs_hm': s.get('hm'), 'obs_ws10': s.get('ws10'), 'obs_tm': s.get('tm')}
            w.writerow(row); seen.add((issue, stn)); added += 1
    n = sum(1 for _ in OUT.open(encoding='utf-8')) - 1
    print('FEATURES_ARCHIVED', json.dumps({'issue': issue, 'hour': hour, 'rows_added': added, 'rows_total': n}))


if __name__ == '__main__':
    main()
