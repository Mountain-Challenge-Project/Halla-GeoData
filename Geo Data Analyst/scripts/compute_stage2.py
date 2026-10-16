"""Stage 2b: run the physics modules over all cells for the current forecast and check them against the AWS stations.

Inputs: outputs/jeju_dashboard/data/{forecast.json, levels.json, obs_latest.json, grid.geojson}
Outputs: Geo Data Analyst/data/physics_latest.json   per-cell summary (counts) + station table with
         plain-lapse, foehn-aware and observed temperature / dew point, and the error statistics.
The same formulas run live in the dashboard (JavaScript); this script is the reference check.
"""
import json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / 'work'))
from physics_modules import magnus_td, cell_state, foehn, dir_index, wind_from_uv  # noqa: E402
from fetch_kma_forecast import dfs_xy, ROOT  # noqa: E402

D = ROOT / 'outputs/jeju_dashboard/data'
fc = json.loads((D / 'forecast.json').read_text('utf-8')); grid = json.loads((D / 'grid.geojson').read_text('utf-8'))
levels = json.loads((D / 'levels.json').read_text('utf-8')) if (D / 'levels.json').exists() else None
obs = json.loads((D / 'obs_latest.json').read_text('utf-8')) if (D / 'obs_latest.json').exists() else None
D2R = math.pi / 180


def centre(f):
    ring = f['geometry']['coordinates'][0]; n = len(ring) - 1
    return sum(q[0] for q in ring[:n]) / n, sum(q[1] for q in ring[:n]) / n


def point_for(lon, lat):
    x, y = dfs_xy(lon, lat); return f'{x},{y}', fc['points'].get(f'{x},{y}')


def cross_wind(key, hour, h):
    L = levels and levels['points'].get(key, {}).get(hour)
    if L and L.get('u850') is not None:
        d, s = wind_from_uv(L['u850'], L['v850']); return d, s, 'KIM 850 hPa'
    try: return float(h['vec']), float(h['wsd']), '10 m forecast'
    except (TypeError, ValueError, KeyError): return None


def upstream(lon, lat, direction, dist_km):
    mlat = 111320; mlon = 111320 * math.cos(lat * D2R)
    for extra in (5, 0, 10, 15):
        d = (dist_km + extra) * 1000
        k, pt = point_for(lon + d * math.sin(direction * D2R) / mlon, lat + d * math.cos(direction * D2R) / mlat)
        if pt: return pt
    return None


def cell_physics(p, lon, lat, hour):
    key, pt = point_for(lon, lat)
    if not pt or hour not in pt['hours']: return None
    h = pt['hours'][hour]
    try: t0, rh0 = float(h['t1h']), float(h['reh'])
    except (TypeError, ValueError): return None
    z0 = pt.get('elev_m') or 0.0; zc = p.get('elev_mean') or 0.0
    st = cell_state(t0, rh0, z0, zc); st['lcl_rel'] = st['lcl_alt'] - zc; st['point'] = key
    w = cross_wind(key, hour, h); st['foehn'] = None
    if w and p.get('up_max'):
        i = dir_index(w[0]); ridge = p['up_max'][i]; dist = p['up_dist'][i]
        up = upstream(lon, lat, w[0], dist)
        if up and hour in up['hours']:
            uh = up['hours'][hour]
            try: f = foehn(float(uh['t1h']), float(uh['reh']), up.get('elev_m') or 0.0, ridge, zc, w[1], ridge - zc)
            except (TypeError, ValueError): f = None
            if f: f.update({'wind_dir': w[0], 'wind_spd': w[1], 'wind_src': w[2], 'upstream_point': f'{up["nx"]},{up["ny"]}'}); st['foehn'] = f
    return st


def main():
    hour = fc['hours'][0]
    cells = {}; counts = {'cells': 0, 'in_cloud': 0, 'dewdep_le1': 0, 'foehn_index_ge1': 0, 'foehn_active': 0, 'no_point': 0}
    for f in grid['features']:
        p = f['properties']; lon, lat = centre(f); st = cell_physics(p, lon, lat, hour)
        if not st: counts['no_point'] += 1; continue
        counts['cells'] += 1; cells[p['grid_id']] = st
        if st['lcl_rel'] <= 0: counts['in_cloud'] += 1
        if st['t'] - st['td'] <= 1: counts['dewdep_le1'] += 1
        if st['foehn'] and st['foehn']['index'] >= 1: counts['foehn_index_ge1'] += 1
        if st['foehn'] and st['foehn']['active']: counts['foehn_active'] += 1
    rows = []
    if obs:
        for stn, s in obs['stations'].items():
            if not s.get('grid_id') or s['grid_id'] not in cells or s.get('ta') in (None, ''): continue
            st = cells[s['grid_id']]; ta = float(s['ta']); td = float(s['td']) if s.get('td') not in (None, '') else None
            fo = st['foehn']; t_f = fo['t'] if fo and fo['active'] else st['t']; td_f = fo['td'] if fo and fo['active'] else st['td']
            rows.append({'stn': stn, 'name': s['name'], 'ht_m': s.get('ht_m'), 'grid_id': s['grid_id'], 'obs_ta': ta, 'obs_td': td, 'obs_tm': s.get('tm'),
                         'lapse_t': round(st['t'], 1), 'lapse_td': round(st['td'], 1), 'foehn_aware_t': round(t_f, 1), 'foehn_aware_td': round(td_f, 1),
                         'foehn_index': round(fo['index'], 1) if fo else None, 'foehn_active': bool(fo and fo['active']), 'wind_src': fo['wind_src'] if fo else None, 'lcl_rel_m': round(st['lcl_rel'])})
    def stats(key, ref):
        e = [r[key] - r[ref] for r in rows if r[ref] is not None]
        return {'n': len(e), 'bias': round(sum(e) / len(e), 2), 'rmse': round(math.sqrt(sum(x * x for x in e) / len(e)), 2)} if e else None
    out = {'forecast_base_kst': fc['base_time_kst'], 'hour': hour, 'kim_issue_utc': levels and levels.get('tmfc_utc'), 'obs_time': obs and obs.get('fetched_at'), 'counts': counts,
           'station_check': {'temperature_lapse': stats('lapse_t', 'obs_ta'), 'temperature_foehn_aware': stats('foehn_aware_t', 'obs_ta'),
                             'dew_point_lapse': stats('lapse_td', 'obs_td'), 'dew_point_foehn_aware': stats('foehn_aware_td', 'obs_td')}, 'stations': rows,
           'note': 'one issue, one minute of observations; physics only, no learned residual; foehn-aware = foehn parcel values where the foehn condition is active, else the lapse values'}
    (HERE.parent / 'data/physics_latest.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print('STAGE2_PHYSICS', json.dumps({k: v for k, v in out.items() if k != 'stations'}, ensure_ascii=False))
    for r in sorted(rows, key=lambda r: -(r['ht_m'] or 0))[:6]:
        print(' ', r['name'], r['ht_m'], 'obs', r['obs_ta'], '/', r['obs_td'], 'lapse', r['lapse_t'], '/', r['lapse_td'], 'foehn idx', r['foehn_index'], 'active' if r['foehn_active'] else '')


if __name__ == '__main__':
    main()
