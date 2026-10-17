"""Stage 5b: fog and heavy-rain case catalogues from the ASOS archive (labels for case validation).

fog hours      visibility VS < 1,000 m (VS is in 10 m units) or present-weather code WW containing fog (code 4x/28),
               with the observed dew-point depression T - Td at that hour -> checks the 'fog possible' rule (<= 1 degC)
heavy-rain     hourly RN >= 20 mm or 3-hour sum >= 60 mm at any station (the KMA heavy-rain advisory scale loosely)
Writes data/fog_cases_asos.csv, data/heavy_rain_cases_asos.csv and data/asos_case_catalogue_summary.json.
"""
import csv, glob, json
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; GDA = HERE.parent
NAMES = {'184': '제주', '185': '고산', '188': '성산', '189': '서귀포'}


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


rows = []
for path in sorted(glob.glob(str(ROOT / 'runtime/kma/obs/asos_hourly/*.csv'))):
    with open(path, encoding='utf-8') as f: rows.extend(csv.DictReader(f))
fog = []; dep_fog = []; dep_all = []
for r in rows:
    vs, ta, td, ww = num(r['VS']), num(r['TA']), num(r['TD']), (r.get('WW') or '')
    if ta is None or td is None: continue
    dep = ta - td; dep_all.append(dep)
    is_fog = (vs is not None and vs * 10 < 1000) or any(c in ww for c in ('40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '28'))
    if is_fog:
        fog.append({'tm': r['TM'], 'station': NAMES.get(r['STN'], r['STN']), 'vis_m': vs * 10 if vs is not None else '', 'ww': ww, 'ta': ta, 'td': td, 'dewdep': round(dep, 1), 'hm': r['HM']}); dep_fog.append(dep)
# heavy rain: per station 1 h and 3 h sums
by_st = {}
for r in rows: by_st.setdefault(r['STN'], {})[r['TM']] = num(r['RN']) or 0.0
heavy = []
for stn, series in by_st.items():
    tms = sorted(series)
    for i, tm in enumerate(tms):
        r1 = series[tm]; r3 = r1 + (series[tms[i - 1]] if i >= 1 else 0) + (series[tms[i - 2]] if i >= 2 else 0)
        if r1 >= 20 or r3 >= 60: heavy.append({'tm': tm, 'station': NAMES.get(stn, stn), 'rn_1h_mm': r1, 'rn_3h_mm': round(r3, 1)})
for name, data, cols in [('fog_cases_asos.csv', fog, ['tm', 'station', 'vis_m', 'ww', 'ta', 'td', 'dewdep', 'hm']), ('heavy_rain_cases_asos.csv', heavy, ['tm', 'station', 'rn_1h_mm', 'rn_3h_mm'])]:
    with (GDA / 'data' / name).open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(sorted(data, key=lambda r: r['tm']))
fog_rule_hit = sum(1 for d in dep_fog if d <= 1.0); all_rule = sum(1 for d in dep_all if d <= 1.0)
summary = {'archive_rows': len(rows), 'fog_hours': len(fog), 'fog_hours_with_dewdep_le1': fog_rule_hit, 'fog_rule_recall_pct': round(100 * fog_rule_hit / len(fog), 1) if fog else None,
           'all_hours_with_dewdep_le1': all_rule, 'fog_rule_precision_pct': round(100 * fog_rule_hit / all_rule, 1) if all_rule else None,
           'fog_by_station': {n: sum(1 for r in fog if r['station'] == n) for n in NAMES.values()}, 'fog_by_month': {m: sum(1 for r in fog if r['tm'][4:6] == m) for m in sorted({r['tm'][4:6] for r in fog})},
           'heavy_rain_hours': len(heavy), 'heavy_rain_by_station': {n: sum(1 for r in heavy if r['station'] == n) for n in NAMES.values()}, 'heavy_rain_by_month': {m: sum(1 for r in heavy if r['tm'][4:6] == m) for m in sorted({r['tm'][4:6] for r in heavy})},
           'note': 'fog rule = dew-point depression <= 1 degC at the station; recall = share of fog hours the rule catches, precision = share of rule hours that are fog (coastal ASOS only, so mountain fog is not represented)'}
(GDA / 'data/asos_case_catalogue_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
print('CASE_CATALOGUE', json.dumps(summary, ensure_ascii=False))
