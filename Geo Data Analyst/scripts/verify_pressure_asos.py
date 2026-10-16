"""Stage 3a: validate the station-pressure module against the ASOS archive (and the AWS minute archive).

For every archived ASOS hour (runtime/kma/obs/asos_hourly/*.csv, 4 Jeju stations since 2023-01) the hypsometric
station pressure from the reported sea-level pressure PS, air temperature TA, dew point TD and the barometer
height (ht_pa_m from data/kma_stations_jeju.csv) is compared with the observed local pressure PA. The AWS minute
archive adds the high stations (PA and PS both reported) for the elevation range the cells need.
Writes data/pressure_module_check.json.
"""
import csv, glob, json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from physics_modules import station_pressure  # noqa: E402
ROOT = HERE.parents[1]; GDA = HERE.parent


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def stats(err):
    if not err: return None
    b = sum(err) / len(err)
    return {'n': len(err), 'bias_hpa': round(b, 2), 'rmse_hpa': round(math.sqrt(sum(e * e for e in err) / len(err)), 2), 'max_abs_hpa': round(max(abs(e) for e in err), 2)}


with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f:
    st = {r['stn']: r for r in csv.DictReader(f)}
out = {'asos': {}, 'aws_min': {}}
for stn in ['184', '185', '188', '189']:
    z = num(st[stn]['ht_pa_m']) or num(st[stn]['ht_m']); err = []; err_dry = []; by_year = {}
    for path in sorted(glob.glob(str(ROOT / 'runtime/kma/obs/asos_hourly/*.csv'))):
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r['STN'] != stn: continue
                ps, pa, ta, td = num(r['PS']), num(r['PA']), num(r['TA']), num(r['TD'])
                if None in (ps, pa, ta) or ps < 900 or pa < 850: continue
                e = station_pressure(ps, ta, z, td) - pa; err.append(e); by_year.setdefault(r['TM'][:4], []).append(e)
                err_dry.append(station_pressure(ps, ta, z) - pa)
    out['asos'][stn] = {'name': st[stn]['name'], 'barometer_height_m': z, 'with_virtual_temperature': stats(err), 'dry_air': stats(err_dry), 'by_year': {y: stats(v) for y, v in sorted(by_year.items())}}
# AWS minute archive: every station that reports both PA and PS
errs = {}
for path in sorted(glob.glob(str(ROOT / 'runtime/kma/obs/aws_min/*.csv'))):
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            s = st.get(r['STN']);
            if not s: continue
            ps, pa, ta, td = num(r['PS']), num(r['PA']), num(r['TA']), num(r['TD'])
            if None in (ps, pa, ta) or ps < 900 or pa < 700: continue
            z = num(s['ht_pa_m']) or num(s['ht_m']) or 0.0
            errs.setdefault(r['STN'], []).append(station_pressure(ps, ta, z, td) - pa)
out['aws_min'] = {k: {'name': st[k]['name'], 'ht_m': num(st[k]['ht_m']), **stats(v)} for k, v in sorted(errs.items(), key=lambda kv: -(num(st[kv[0]]['ht_m']) or 0))}
all_e = [e for d in out['asos'].values() for _ in [0] for e in []]
out['summary'] = {'asos_overall_rmse_hpa': round(math.sqrt(sum(d['with_virtual_temperature']['rmse_hpa'] ** 2 * d['with_virtual_temperature']['n'] for d in out['asos'].values()) / sum(d['with_virtual_temperature']['n'] for d in out['asos'].values())), 2),
                  'note': 'PS is KMA\'s own sea-level reduction of PA, so this checks that the module inverts it consistently (layer temperature, moisture); the AWS high stations show the error growth with height'}
(GDA / 'data/pressure_module_check.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print('PRESSURE_CHECK', json.dumps({'summary': out['summary'], 'asos': {k: v['with_virtual_temperature'] for k, v in out['asos'].items()},
                                    'aws_top': {k: {'name': v['name'], 'ht_m': v['ht_m'], 'bias': v['bias_hpa'], 'rmse': v['rmse_hpa'], 'n': v['n']} for k, v in list(out['aws_min'].items())[:4]}}, ensure_ascii=False))
