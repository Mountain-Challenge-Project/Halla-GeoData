"""Stage 3c: station-based verification that accumulates over time.

Each run appends the station rows of data/physics_latest.json (one forecast issue x one observation minute, from
compute_stage2.py) to runtime/kma/verification/stationwise.csv (local archive) and recomputes the summary over the
whole archive into data/verification_summary.json:
  - temperature: raw 5 km point value (= the 'no correction' control), lapse-corrected (linear control), foehn-aware
  - dew point: lapse-corrected, foehn-aware
  - broken down by elevation band (<300, 300-1000, >=1000 m), hour of day (KST) and foehn-condition flag
Run it after compute_stage2.py (RUN_PIPELINE.cmd does the whole chain). The summary becomes meaningful after weeks.
"""
import csv, json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; GDA = HERE.parent
ARCH = ROOT / 'runtime/kma/verification/stationwise.csv'
COLS = ['issue_kst', 'hour', 'obs_tm', 'stn', 'name', 'ht_m', 'grid_id', 'obs_ta', 'obs_td', 'raw_t1h', 'lapse_t', 'foehn_aware_t', 'lapse_td', 'foehn_aware_td', 'foehn_index', 'foehn_active', 'wind_src', 'lcl_rel_m']


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def append_current():
    ph = json.loads((GDA / 'data/physics_latest.json').read_text('utf-8'))
    fc = json.loads((ROOT / 'outputs/jeju_dashboard/data/forecast.json').read_text('utf-8'))
    sys.path.insert(0, str(ROOT / 'work')); from fetch_kma_forecast import dfs_xy  # noqa: E402
    stations = {}
    with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f): stations[r['stn']] = r
    ARCH.parent.mkdir(parents=True, exist_ok=True); new = not ARCH.exists(); seen = set()
    if not new:
        with ARCH.open(encoding='utf-8') as f:
            for r in csv.DictReader(f): seen.add((r['issue_kst'], r['stn']))
    added = 0
    with ARCH.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new: w.writeheader()
        for r in ph['stations']:
            key = (ph['forecast_base_kst'], r['stn'])
            if key in seen: continue
            s = stations[r['stn']]; x, y = dfs_xy(float(s['lon']), float(s['lat'])); pt = fc['points'].get(f'{x},{y}'); raw = num(pt['hours'][ph['hour']]['t1h']) if pt and ph['hour'] in pt['hours'] else None
            w.writerow({'issue_kst': ph['forecast_base_kst'], 'hour': ph['hour'], 'obs_tm': r.get('obs_tm'), 'stn': r['stn'], 'name': r['name'], 'ht_m': r['ht_m'], 'grid_id': r['grid_id'], 'obs_ta': r['obs_ta'], 'obs_td': r['obs_td'],
                        'raw_t1h': raw, 'lapse_t': r['lapse_t'], 'foehn_aware_t': r['foehn_aware_t'], 'lapse_td': r['lapse_td'], 'foehn_aware_td': r['foehn_aware_td'], 'foehn_index': r['foehn_index'], 'foehn_active': r['foehn_active'], 'wind_src': r['wind_src'], 'lcl_rel_m': r['lcl_rel_m']})
            seen.add(key); added += 1
    return added


def stats(pairs):
    e = [a - b for a, b in pairs if a is not None and b is not None]
    if not e: return None
    return {'n': len(e), 'bias': round(sum(e) / len(e), 2), 'rmse': round(math.sqrt(sum(x * x for x in e) / len(e)), 2)}


def summarize():
    rows = []
    with ARCH.open(encoding='utf-8') as f:
        for r in csv.DictReader(f): rows.append(r)
    issues = sorted({r['issue_kst'] for r in rows})
    def block(rs):
        return {'temperature': {'raw_5km_point': stats([(num(r['raw_t1h']), num(r['obs_ta'])) for r in rs]), 'lapse_corrected': stats([(num(r['lapse_t']), num(r['obs_ta'])) for r in rs]), 'foehn_aware': stats([(num(r['foehn_aware_t']), num(r['obs_ta'])) for r in rs])},
                'dew_point': {'lapse_corrected': stats([(num(r['lapse_td']), num(r['obs_td'])) for r in rs]), 'foehn_aware': stats([(num(r['foehn_aware_td']), num(r['obs_td'])) for r in rs])}}
    def band(r):
        h = num(r['ht_m']) or 0; return '<300 m' if h < 300 else ('300-1000 m' if h < 1000 else '>=1000 m')
    out = {'issues': len(issues), 'first_issue': issues[0] if issues else None, 'last_issue': issues[-1] if issues else None, 'station_rows': len(rows), 'overall': block(rows),
           'by_elevation': {b: block([r for r in rows if band(r) == b]) for b in ['<300 m', '300-1000 m', '>=1000 m']},
           'by_hour_kst': {h: block([r for r in rows if r['hour'][8:10] == h]) for h in sorted({r['hour'][8:10] for r in rows})},
           'foehn_active_rows': block([r for r in rows if r['foehn_active'] == 'True']),
           'improvement_vs_raw_pct': None,
           'note': 'accumulates one row per station per pipeline run; raw = 5 km point value applied to the cell (no correction), lapse = linear control, foehn-aware = stage-2 physics; needs weeks of runs before the numbers mean much'}
    o = out['overall']['temperature']
    if o['raw_5km_point'] and o['lapse_corrected']:
        out['improvement_vs_raw_pct'] = {'lapse_rmse': round(100 * (1 - o['lapse_corrected']['rmse'] / o['raw_5km_point']['rmse']), 1), 'foehn_aware_rmse': round(100 * (1 - o['foehn_aware']['rmse'] / o['raw_5km_point']['rmse']), 1) if o['foehn_aware'] else None}
    (GDA / 'data/verification_summary.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    # uncertainty for the dashboard: RMSE of the physics estimate by elevation band (stage 5 confidence display)
    unc = {'schema_version': 1, 'issues': len(issues), 'rows': len(rows), 'last_issue': issues[-1] if issues else None, 'by_elevation': {}}
    for b, blk in out['by_elevation'].items():
        t = blk['temperature']['lapse_corrected']; td = blk['dew_point']['lapse_corrected']
        unc['by_elevation'][b] = {'n': t['n'] if t else 0, 't_bias': t['bias'] if t else None, 't_rmse': t['rmse'] if t else None, 'td_bias': td['bias'] if td else None, 'td_rmse': td['rmse'] if td else None}
    unc['note'] = 'station-level error of the physics estimate accumulated over the pipeline runs; shown as +-RMSE in the cell detail'
    (ROOT / 'outputs/jeju_dashboard/data/uncertainty.json').write_text(json.dumps(unc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return out


if __name__ == '__main__':
    added = append_current(); s = summarize()
    print('VERIFY_STATIONS', json.dumps({'rows_added': added, 'issues': s['issues'], 'rows': s['station_rows'], 'overall': s['overall'], 'improvement_vs_raw_pct': s['improvement_vs_raw_pct']}, ensure_ascii=False))
