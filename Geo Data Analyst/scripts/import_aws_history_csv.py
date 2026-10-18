"""Import AWS hourly history CSVs (outputs/jeju_weather/<date>/csv/aws_hourly_snapshot_<stn>_*.csv from the collectors
merged in PR #17, or 기상자료개방포털 exports converted to the same columns) into runtime/kma/obs/aws_hourly/<YYYYMM>.csv,
the station-hour archive that build_training_set_era5.py pairs with the reanalysis inputs.

Columns written: TM (KST YYYYMMDDHHMM), STN, TA, TD, HM, WS, WD, PA, PS, RN60. Rows whose temperature is missing are
skipped; existing (TM, STN) pairs are not duplicated.
"""
import csv, glob, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
OUT = ROOT / 'runtime/kma/obs/aws_hourly'; OUT.mkdir(parents=True, exist_ok=True)
pattern = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / 'outputs/jeju_weather/*/csv/aws_hourly_snapshot_*.csv')
COLS = ['TM', 'STN', 'TA', 'TD', 'HM', 'WS', 'WD', 'PA', 'PS', 'RN60']
seen = {}
for p in glob.glob(str(OUT / '*.csv')):
    for r in csv.DictReader(open(p, encoding='utf-8')): seen.setdefault(Path(p).stem, set()).add((r['TM'], r['STN']))
added = 0; by_month = {}
for path in sorted(glob.glob(pattern)):
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if not r.get('temperature_c'): continue
            kst = r['observed_at_kst']; tm = kst[:4] + kst[5:7] + kst[8:10] + kst[11:13] + kst[14:16]; stn = r['station_id']
            if (tm, stn) in seen.get(tm[:6], set()): continue
            by_month.setdefault(tm[:6], []).append({'TM': tm, 'STN': stn, 'TA': r['temperature_c'], 'TD': r.get('dewpoint_c', ''), 'HM': r.get('relative_humidity_pct', ''), 'WS': r.get('wind_speed_ms', ''), 'WD': r.get('wind_direction_deg', ''),
                                                  'PA': r.get('station_pressure_hpa', ''), 'PS': r.get('sea_level_pressure_hpa', ''), 'RN60': r.get('rainfall_60min_mm', '')})
            seen.setdefault(tm[:6], set()).add((tm, stn)); added += 1
for m, rows in by_month.items():
    path = OUT / f'{m}.csv'; new = not path.exists()
    with path.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new: w.writeheader()
        w.writerows(rows)
print('AWS_HISTORY_IMPORTED', {'rows_added': added, 'months': sorted(by_month), 'stations': sorted({r['STN'] for rs in by_month.values() for r in rs})})
