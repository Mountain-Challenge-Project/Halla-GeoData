"""FALLBACK (차선) source, second to Copernicus CDS ERA5 originals. External data without an account: ERA5-Land / ERA5 hourly history at the Jeju stations from the Open-Meteo archive API.

Open-Meteo (https://open-meteo.com, CC-BY 4.0, free for non-commercial use, no key) serves the Copernicus ERA5-Land
(9 km) and ERA5 (25 km) reanalyses as hourly point series. For every station in data/kma_stations_jeju.csv this
script downloads, per calendar year since START:
  era5_land : temperature_2m, dew_point_2m, relative_humidity_2m, surface_pressure, pressure_msl, wind_speed_10m,
              wind_direction_10m, precipitation, cloud_cover, shortwave_radiation
  era5      : temperature / relative_humidity / wind_speed / wind_direction / geopotential_height at 925 and 850 hPa
These are the past grid inputs that pair with the ASOS (and later AWS) archive for the residual-learning model,
in place of the forecast issues that do not exist for past dates. ERA5 lags real time by about 5 days.
Writes runtime/kma/era5/<stn>_<model>_<year>.csv (local) and Geo Data Analyst/data/era5_openmeteo_manifest.json.
"""
import csv, json, sys, time, datetime as dt, hashlib, urllib.request, urllib.parse, urllib.error
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; GDA = HERE.parent
OUT = ROOT / 'runtime/kma/era5'; START = 2023
API = 'https://archive-api.open-meteo.com/v1/archive'
LAND = 'temperature_2m,dew_point_2m,relative_humidity_2m,surface_pressure,pressure_msl,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,shortwave_radiation'
PRS = ','.join(f'{v}_{lvl}hPa' for lvl in (925, 850) for v in ('temperature', 'relative_humidity', 'wind_speed', 'wind_direction', 'geopotential_height'))


def fetch(params, tries=4):
    url = API + '?' + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Halla-GeoData/1.0'}), timeout=120) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(60 * (i + 1)); continue
            if i < tries - 1: time.sleep(10); continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if i < tries - 1: time.sleep(10); continue
            raise


def main():
    with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f: stations = [r for r in csv.DictReader(f)]
    only = sys.argv[1:]  # optional station ids
    OUT.mkdir(parents=True, exist_ok=True); man_path = GDA / 'data/era5_openmeteo_manifest.json'
    man = json.loads(man_path.read_text('utf-8')) if man_path.exists() else {'source': 'Open-Meteo archive API (ERA5-Land, ERA5), CC-BY 4.0; data: Copernicus Climate Change Service ERA5 / ERA5-Land', 'api': API, 'files': {}}
    today = dt.date.today(); end_all = today - dt.timedelta(days=6)
    done = 0; skipped = 0
    for s in stations:
        if only and s['stn'] not in only: continue
        for year in range(START, today.year + 1):
            d0 = dt.date(year, 1, 1); d1 = min(dt.date(year, 12, 31), end_all)
            if d0 > d1: continue
            for model, hourly in (('era5_land', LAND), ('era5', PRS)):
                name = f"{s['stn']}_{model}_{year}.csv"; path = OUT / name
                if name in man['files'] and path.exists() and man['files'][name].get('end') == d1.isoformat(): skipped += 1; continue
                d = fetch({'latitude': s['lat'], 'longitude': s['lon'], 'start_date': d0.isoformat(), 'end_date': d1.isoformat(), 'hourly': hourly, 'models': model, 'timezone': 'Asia/Seoul'})
                h = d['hourly']; cols = list(h.keys())
                with path.open('w', newline='', encoding='utf-8') as f:
                    w = csv.writer(f); w.writerow(cols); w.writerows(zip(*[h[c] for c in cols]))
                valid = sum(1 for v in h[cols[1]] if v is not None)
                man['files'][name] = {'stn': s['stn'], 'name': s['name'], 'model': model, 'lat': float(s['lat']), 'lon': float(s['lon']), 'model_elevation_m': d.get('elevation'), 'start': d0.isoformat(), 'end': d1.isoformat(),
                                      'rows': len(h['time']), 'valid_rows': valid, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'downloaded_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
                done += 1; print(f'  {name}: {len(h["time"])} rows, {valid} valid, model elev {d.get("elevation")} m', flush=True)
                man_path.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding='utf-8'); time.sleep(1.2)
    print('ERA5_OPENMETEO_DONE', json.dumps({'files_new': done, 'files_skipped': skipped, 'files_total': len(man['files']), 'end': end_all.isoformat()}))


if __name__ == '__main__':
    main()
