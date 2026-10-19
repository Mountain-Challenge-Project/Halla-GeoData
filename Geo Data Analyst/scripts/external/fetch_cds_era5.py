"""PRIMARY (1순위) ERA5 originals from the Copernicus Climate Data Store for the Jeju stations.

Needs CDS_API_KEY in .env (Personal Access Token from https://cds.climate.copernicus.eu profile; the dataset licences
must be accepted once on the website) and the cdsapi package (pip install cdsapi). Downloads, per calendar year since
START, the hourly ERA5-Land surface variables and the ERA5 925/850 hPa level variables for the box
33.0-33.7N / 126.0-127.1E as NetCDF into runtime/kma/era5_cds/, then samples the nearest grid point for each station
and writes runtime/kma/era5_cds/<stn>.csv with the SAME columns the Open-Meteo fallback uses, so
build_training_set_era5.py prefers these files automatically (it checks runtime/kma/era5_cds/<stn>.csv first).
"""
import csv, json, sys, datetime as dt
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]; GDA = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'work')); from env_config import env_value  # noqa: E402
OUT = ROOT / 'runtime/kma/era5_cds'; START = 2023; AREA = [33.7, 126.0, 33.0, 127.1]
LAND_VARS = ['2m_temperature', '2m_dewpoint_temperature', 'surface_pressure', '10m_u_component_of_wind', '10m_v_component_of_wind', 'total_precipitation', 'surface_solar_radiation_downwards']
PRS_VARS = ['temperature', 'relative_humidity', 'u_component_of_wind', 'v_component_of_wind', 'geopotential']


def main():
    key = env_value('CDS_API_KEY')
    if not key:
        print('CDS_API_KEY가 비어 있습니다. https://cds.climate.copernicus.eu 에서 로그인 후 프로필의 Personal Access Token을 .env의 CDS_API_KEY= 뒤에 붙여 넣고, 데이터셋 페이지에서 라이선스를 한 번 수락하세요.'); return 2
    try: import cdsapi, xarray as xr, numpy as np
    except ImportError as e:
        print(f'필요한 패키지가 없습니다 ({e.name}). anaconda Python에서: pip install cdsapi xarray netCDF4'); return 2
    c = cdsapi.Client(url='https://cds.climate.copernicus.eu/api', key=key, quiet=True); OUT.mkdir(parents=True, exist_ok=True)
    year_end = dt.date.today().year
    for year in range(START, year_end + 1):
        months = [f'{m:02d}' for m in range(1, 13)]
        land = OUT / f'era5_land_{year}.nc'
        if not land.exists():
            c.retrieve('reanalysis-era5-land', {'variable': LAND_VARS, 'year': str(year), 'month': months, 'day': [f'{d:02d}' for d in range(1, 32)], 'time': [f'{h:02d}:00' for h in range(24)], 'area': AREA, 'format': 'netcdf'}, str(land)); print('downloaded', land.name)
        prs = OUT / f'era5_prs_{year}.nc'
        if not prs.exists():
            c.retrieve('reanalysis-era5-pressure-levels', {'product_type': 'reanalysis', 'variable': PRS_VARS, 'pressure_level': ['925', '850'], 'year': str(year), 'month': months, 'day': [f'{d:02d}' for d in range(1, 32)], 'time': [f'{h:02d}:00' for h in range(24)], 'area': AREA, 'format': 'netcdf'}, str(prs)); print('downloaded', prs.name)
    # station point series in the fallback's column names
    with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f: stations = list(csv.DictReader(f))
    land = xr.open_mfdataset(str(OUT / 'era5_land_*.nc')); prs = xr.open_mfdataset(str(OUT / 'era5_prs_*.nc'))
    for s in stations:
        la = land.sel(latitude=float(s['lat']), longitude=float(s['lon']), method='nearest'); pa = prs.sel(latitude=float(s['lat']), longitude=float(s['lon']), method='nearest')
        t = (la['t2m'] - 273.15).values; td = (la['d2m'] - 273.15).values; sp = la['sp'].values / 100; u, v = la['u10'].values, la['v10'].values
        times = [str(x)[:16] for x in la['time'].values]
        with (OUT / f"{s['stn']}.csv").open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f); w.writerow(['time', 'temperature_2m', 'dew_point_2m', 'relative_humidity_2m', 'surface_pressure', 'wind_speed_10m', 'wind_direction_10m', 'precipitation', 'shortwave_radiation',
                                           'temperature_925hPa', 'relative_humidity_925hPa', 'wind_speed_925hPa', 'wind_direction_925hPa', 'temperature_850hPa', 'relative_humidity_850hPa', 'wind_speed_850hPa', 'wind_direction_850hPa'])
            import math
            for i, tm in enumerate(times):
                tt, dd = float(t[i]), float(td[i]); rh = 100 * math.exp(17.62 * dd / (243.12 + dd)) / math.exp(17.62 * tt / (243.12 + tt))
                ws = math.hypot(u[i], v[i]) * 3.6; wd = (math.degrees(math.atan2(-u[i], -v[i])) + 360) % 360
                row = [tm.replace(' ', 'T'), round(tt, 2), round(dd, 2), round(rh, 1), round(float(sp[i]), 1), round(ws, 1), round(wd), round(float(la['tp'].values[i]) * 1000, 2), round(float(la['ssrd'].values[i]) / 3600, 1)]
                for lvl in (925, 850):
                    q = pa.sel(pressure_level=lvl) if 'pressure_level' in pa.dims else pa.sel(level=lvl)
                    uu, vv = float(q['u'].values[i]), float(q['v'].values[i])
                    row += [round(float(q['t'].values[i]) - 273.15, 2), round(float(q['r'].values[i]), 1), round(math.hypot(uu, vv) * 3.6, 1), round((math.degrees(math.atan2(-uu, -vv)) + 360) % 360)]
                w.writerow(row)
        print('station series', s['stn'], s['name'])
    print('CDS_ERA5_DONE', {'stations': len(stations), 'years': list(range(START, year_end + 1))})


if __name__ == '__main__':
    sys.exit(main())
