"""Stage 3b: foehn candidate events from the ASOS archive (case labels for the stage-5 case validation).

Jeju's four ASOS stations form two cross-island pairs around Hallasan:
  E-W axis : 성산 188 (east coast)  <->  고산 185 (west coast)
  N-S axis : 제주 184 (north coast) <->  서귀포 189 (south coast)
For every archived hour the windward/lee roles follow the windward station's wind direction (within +-50 deg of
the pair axis). An hour is a foehn candidate when
  windward wind >= WS_MIN m/s, lee T - windward T >= DT_MIN degC, lee RH <= windward RH - DRH_MIN %p, lee RH <= 70 %.
Consecutive candidate hours (gap <= 2 h) form one event. Writes data/foehn_cases_asos.csv and a summary JSON.
This is a screening on coastal stations; it cannot see foehn that ends on the mountain slopes.
"""
import csv, glob, json, math
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; GDA = HERE.parent
WS_MIN, DT_MIN, DRH_MIN = 6.0, 3.0, 15.0
PAIRS = [{'axis': 'E-W', 'a': '188', 'b': '185', 'a_dir': 90, 'b_dir': 270}, {'axis': 'N-S', 'a': '184', 'b': '189', 'a_dir': 0, 'b_dir': 180}]
NAMES = {'184': '제주', '185': '고산', '188': '성산', '189': '서귀포'}


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def angdiff(a, b):
    d = abs((a - b + 180) % 360 - 180); return d


rows = {}
for path in sorted(glob.glob(str(ROOT / 'runtime/kma/obs/asos_hourly/*.csv'))):
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.setdefault(r['TM'], {})[r['STN']] = r
cands = []
for tm in sorted(rows):
    h = rows[tm]
    for pr in PAIRS:
        for wind_stn, lee_stn, wdir in [(pr['a'], pr['b'], pr['a_dir']), (pr['b'], pr['a'], pr['b_dir'])]:
            w, l = h.get(wind_stn), h.get(lee_stn)
            if not w or not l: continue
            wd, ws = num(w['WD']), num(w['WS']); ta_w, ta_l = num(w['TA']), num(l['TA']); rh_w, rh_l = num(w['HM']), num(l['HM'])
            if None in (wd, ws, ta_w, ta_l, rh_w, rh_l): continue
            wd_deg = wd * 10 if wd <= 36 else wd      # ASOS WD is in 36-point code (x10 degrees)
            if ws < WS_MIN or angdiff(wd_deg, wdir) > 50: continue
            dt, drh = ta_l - ta_w, rh_w - rh_l
            if dt >= DT_MIN and drh >= DRH_MIN and rh_l <= 70:
                cands.append({'tm': tm, 'axis': pr['axis'], 'windward': NAMES[wind_stn], 'lee': NAMES[lee_stn], 'wind_dir_deg': wd_deg, 'wind_ms': ws, 'dT_lee_minus_windward': round(dt, 1), 'dRH_windward_minus_lee': round(drh, 1), 'lee_T': ta_l, 'lee_RH': rh_l, 'windward_T': ta_w, 'windward_RH': rh_w})
# group into events
events = []
for c in cands:
    t = int(c['tm'][:10]); key = (c['axis'], c['lee'])
    if events and events[-1]['key'] == key and t - events[-1]['last'] <= 2 and events[-1]['last_tm'][:8] == c['tm'][:8]:
        e = events[-1]; e['hours'] += 1; e['last'] = t; e['last_tm'] = c['tm']; e['max_dT'] = max(e['max_dT'], c['dT_lee_minus_windward']); e['max_dRH'] = max(e['max_dRH'], c['dRH_windward_minus_lee']); e['max_wind'] = max(e['max_wind'], c['wind_ms'])
    else:
        events.append({'key': key, 'start_tm': c['tm'], 'last_tm': c['tm'], 'last': t, 'axis': c['axis'], 'windward': c['windward'], 'lee': c['lee'], 'hours': 1, 'max_dT': c['dT_lee_minus_windward'], 'max_dRH': c['dRH_windward_minus_lee'], 'max_wind': c['wind_ms']})
with (GDA / 'data/foehn_cases_asos.csv').open('w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['start_tm', 'last_tm', 'hours', 'axis', 'windward', 'lee', 'max_dT', 'max_dRH', 'max_wind']); w.writeheader()
    for e in events: w.writerow({k: e[k] for k in w.fieldnames})
by_month = {}; by_lee = {}
for e in events: by_month[e['start_tm'][4:6]] = by_month.get(e['start_tm'][4:6], 0) + 1; by_lee[e['lee']] = by_lee.get(e['lee'], 0) + 1
summary = {'archive_hours': len(rows), 'criteria': {'windward_wind_ms_min': WS_MIN, 'dT_min_degC': DT_MIN, 'dRH_min_pct': DRH_MIN, 'lee_RH_max': 70, 'direction_tolerance_deg': 50}, 'candidate_hours': len(cands), 'events': len(events),
           'events_by_month': dict(sorted(by_month.items())), 'events_by_lee_station': by_lee, 'strongest': sorted(events, key=lambda e: -e['max_dT'])[:8],
           'note': 'coastal-station screening only; use as case labels (stage 5) and to pick days for AWS-based transect checks'}
for e in summary['strongest']: e.pop('key', None); e.pop('last', None)
(GDA / 'data/foehn_cases_asos_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
print('FOEHN_CASES', json.dumps({k: v for k, v in summary.items() if k != 'strongest'}, ensure_ascii=False))
for e in summary['strongest'][:5]: print(' ', e['start_tm'], e['axis'], e['windward'], '->', e['lee'], 'h', e['hours'], 'dT', e['max_dT'], 'dRH', e['max_dRH'], 'wind', e['max_wind'])
