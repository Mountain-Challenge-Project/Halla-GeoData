"""Historical training set: ASOS/AWS hourly observations paired with reanalysis inputs (stage-4 archive extension).

Primary source (1순위) : Copernicus CDS ERA5 originals in runtime/kma/era5_cds/<stn>.csv (same columns as below) when present.
Fallback (차선)        : Open-Meteo ERA5-Land / ERA5 CSVs from fetch_era5_openmeteo.py in runtime/kma/era5/.
Targets                : runtime/kma/obs/asos_hourly/*.csv (2023-01..) and, when present, runtime/kma/obs/aws_hourly/*.csv
                         (AWS hourly history from the 기상자료개방포털 CSV, 1순위 for the high stations).

For every station-hour with an observation and a reanalysis value, the row carries the same feature names as the
live archive (archive_features.py) so train_residual_model.py can use both: the reanalysis 2 m values play the role
of the 5 km forecast point (t1h, reh, wsd, vec), the reanalysis model elevation the role of the point elevation,
and the physics (lapse_t, lapse_td, lcl_rel_m) is computed the same way. Foehn fields are left empty (no upstream
point in a point series) and KIM fields are filled from the ERA5 925/850 hPa levels.
Writes runtime/kma/verification/features_era5.csv and data/training_set_era5_summary.json.
"""
import csv, glob, json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); ROOT = HERE.parents[1]; GDA = HERE.parent
from physics_modules import cell_state, magnus_td  # noqa: E402
OUT = ROOT / 'runtime/kma/verification/features_era5.csv'
COLS = ['issue_kst', 'hour', 'stn', 'name', 'grid_id', 'source', 'hour_kst', 'month', 'doy_sin', 'doy_cos', 'stn_ht_m', 'cell_elev_m', 'pt_elev_m', 'dz_cell_pt', 'mean_deg', 'asp_sin', 'asp_cos', 'asp_r',
        'tpi_1km_m', 'svf', 'coast_km', 'ridge_m', 'lee_m', 'lc_tree', 'lc_grass', 'lc_crop', 'lc_builtup', 'lc_water', 'canopy_mean_m', 't1h', 'reh', 'wsd', 'vec_sin', 'vec_cos', 'rn1_mm', 'sky', 'pty',
        't850', 'rh850', 'u850', 'v850', 't925', 'rh925', 'u925', 'v925', 'lapse_t', 'lapse_td', 'lcl_rel_m', 'foehn_index', 'foehn_active', 'foehn_t', 'foehn_td', 'obs_ta', 'obs_td', 'obs_hm', 'obs_ws10', 'obs_tm']
DIRS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def load_series(stn):
    """{hour_kst 'YYYYMMDDHH00': {...}} from CDS originals if present, else Open-Meteo files; returns (dict, source, model_elev)."""
    cds = ROOT / 'runtime/kma/era5_cds' / f'{stn}.csv'
    if cds.exists():
        rows = {r['time']: r for r in csv.DictReader(cds.open(encoding='utf-8'))}; return rows, 'era5_cds', None
    land = {}; prs = {}; elev = None
    man = json.loads((GDA / 'data/era5_openmeteo_manifest.json').read_text('utf-8'))['files'] if (GDA / 'data/era5_openmeteo_manifest.json').exists() else {}
    for path in sorted(glob.glob(str(ROOT / 'runtime/kma/era5' / f'{stn}_era5_land_*.csv'))):
        name = Path(path).name; elev = man.get(name, {}).get('model_elevation_m', elev)
        for r in csv.DictReader(open(path, encoding='utf-8')): land[r['time']] = r
    for path in sorted(glob.glob(str(ROOT / 'runtime/kma/era5' / f'{stn}_era5_*.csv'))):
        if '_era5_land_' in path: continue
        for r in csv.DictReader(open(path, encoding='utf-8')): prs[r['time']] = r
    out = {}
    for t, r in land.items():
        p = prs.get(t, {}); out[t] = {**r, **{k: v for k, v in p.items() if k != 'time'}}
    return out, 'era5_openmeteo', elev


def main():
    with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f: stations = {r['stn']: r for r in csv.DictReader(f)}
    grid = {f['properties']['grid_id']: f['properties'] for f in json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8'))['features']}
    obs = {}
    for path in sorted(glob.glob(str(ROOT / 'runtime/kma/obs/asos_hourly/*.csv'))) + sorted(glob.glob(str(ROOT / 'runtime/kma/obs/aws_hourly/*.csv'))):
        for r in csv.DictReader(open(path, encoding='utf-8')): obs.setdefault(r['STN'], {})[r['TM']] = r
    OUT.parent.mkdir(parents=True, exist_ok=True); n = 0; per = {}; sources = {}
    with OUT.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for stn, series in obs.items():
            s = stations.get(stn)
            if not s or not s['grid_id'] or s['grid_id'] not in grid: continue
            p = grid[s['grid_id']]; era, src, melev = load_series(stn)
            if not era: continue
            sources[stn] = src; melev = melev if melev is not None else (num(s['ht_m']) or 0.0)
            asp = p.get('asp_deg'); z_stn = num(s['ht_m']) or p.get('elev_mean') or 0.0
            for tm, o in series.items():
                key = tm[:4] + '-' + tm[4:6] + '-' + tm[6:8] + 'T' + tm[8:10] + ':00'
                e = era.get(key)
                if not e: continue
                t0, rh0, wsd, vec = num(e.get('temperature_2m')), num(e.get('relative_humidity_2m')), num(e.get('wind_speed_10m')), num(e.get('wind_direction_10m'))
                ta, td = num(o.get('TA')), num(o.get('TD'))
                if None in (t0, rh0, ta): continue
                wsd = (wsd or 0) / 3.6                                    # Open-Meteo wind is km/h
                st = cell_state(t0, rh0, melev, z_stn)                    # physics to the station height from the model point
                dtm = __import__('datetime').datetime.strptime(tm, '%Y%m%d%H%M'); doy = dtm.timetuple().tm_yday
                prec = num(e.get('precipitation')) or 0.0; cc = num(e.get('cloud_cover'))
                ws850 = num(e.get('wind_speed_850hPa')); wd850 = num(e.get('wind_direction_850hPa')); ws925 = num(e.get('wind_speed_925hPa')); wd925 = num(e.get('wind_direction_925hPa'))
                def uv(ws, wd):
                    if ws is None or wd is None: return '', ''
                    ws = ws / 3.6; return round(-ws * math.sin(math.radians(wd)), 2), round(-ws * math.cos(math.radians(wd)), 2)
                u850, v850 = uv(ws850, wd850); u925, v925 = uv(ws925, wd925)
                row = {'issue_kst': 'reanalysis', 'hour': tm, 'stn': stn, 'name': s['name'], 'grid_id': s['grid_id'], 'source': src, 'hour_kst': int(tm[8:10]), 'month': int(tm[4:6]),
                       'doy_sin': round(math.sin(2 * math.pi * doy / 365.25), 4), 'doy_cos': round(math.cos(2 * math.pi * doy / 365.25), 4), 'stn_ht_m': z_stn, 'cell_elev_m': round(p.get('elev_mean') or 0, 1), 'pt_elev_m': melev,
                       'dz_cell_pt': round(z_stn - melev, 1), 'mean_deg': p.get('mean_deg'), 'asp_sin': round(math.sin(math.radians(asp)), 4) if asp is not None else '', 'asp_cos': round(math.cos(math.radians(asp)), 4) if asp is not None else '',
                       'asp_r': p.get('asp_r', ''), 'tpi_1km_m': p.get('tpi_1km_m'), 'svf': p.get('svf'), 'coast_km': p.get('coast_km'),
                       'ridge_m': p['up_max'][int(round(((vec or 0) % 360) / 22.5)) % 16] if p.get('up_max') and vec is not None else '', 'lee_m': (p['up_max'][int(round(((vec or 0) % 360) / 22.5)) % 16] - (p.get('elev_mean') or 0)) if p.get('up_max') and vec is not None else '',
                       'lc_tree': p.get('lc_tree', ''), 'lc_grass': p.get('lc_grass', ''), 'lc_crop': p.get('lc_crop', ''), 'lc_builtup': p.get('lc_builtup', ''), 'lc_water': p.get('lc_water', ''), 'canopy_mean_m': p.get('canopy_mean_m', ''),
                       't1h': t0, 'reh': rh0, 'wsd': round(wsd, 2), 'vec_sin': round(math.sin(math.radians(vec)), 4) if vec is not None else '', 'vec_cos': round(math.cos(math.radians(vec)), 4) if vec is not None else '',
                       'rn1_mm': prec, 'sky': (1 if cc is not None and cc < 30 else 3 if cc is not None and cc < 80 else 4 if cc is not None else ''), 'pty': 1 if prec > 0 else 0,
                       't850': e.get('temperature_850hPa', ''), 'rh850': e.get('relative_humidity_850hPa', ''), 'u850': u850, 'v850': v850, 't925': e.get('temperature_925hPa', ''), 'rh925': e.get('relative_humidity_925hPa', ''), 'u925': u925, 'v925': v925,
                       'lapse_t': round(st['t'], 2), 'lapse_td': round(st['td'], 2), 'lcl_rel_m': round(st['lcl_alt'] - z_stn), 'foehn_index': '', 'foehn_active': 0, 'foehn_t': '', 'foehn_td': '',
                       'obs_ta': ta, 'obs_td': td if td is not None else '', 'obs_hm': o.get('HM', ''), 'obs_ws10': o.get('WS', ''), 'obs_tm': tm}
                w.writerow(row); n += 1; per[stn] = per.get(stn, 0) + 1
    summ = {'rows': n, 'stations': {stations[k]['name']: v for k, v in per.items()}, 'sources': sources, 'file': str(OUT.relative_to(ROOT)), 'note': 'reanalysis-based rows for the residual model; CDS originals take precedence over the Open-Meteo fallback when present'}
    (GDA / 'data/training_set_era5_summary.json').write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding='utf-8')
    print('TRAINING_SET_ERA5', json.dumps(summ, ensure_ascii=False))


if __name__ == '__main__':
    main()
