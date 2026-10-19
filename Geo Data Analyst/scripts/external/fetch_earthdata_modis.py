"""MODIS point series for the Jeju stations through NASA AppEEARS (needs EARTHDATA_USER / EARTHDATA_PASS in .env).

Submits one AppEEARS point task for the 42 stations with
  MOD11A1.061 LST_Day_1km, LST_Night_1km          (land surface temperature)
  MOD07_L2 is not an AppEEARS product; MOD07 profiles come from LAADS instead (see README) -> here MYD21A1D/N LST as well
  MCD43A3.061 Albedo_WSA_shortwave                  (albedo for the Bird clear-sky radiation model)
  MOD13A2.061 _1_km_16_days_NDVI / EVI             (vegetation state)
from START to yesterday, waits for completion and saves the CSV bundle to runtime/kma/modis_appeears/.
Usage: python fetch_earthdata_modis.py [--start 2023-01-01] [--poll]   (--poll waits; without it the task id is saved and
the script can be re-run later to download).
"""
import csv, json, sys, time, datetime as dt, base64, urllib.request, urllib.error, zipfile, io
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]; GDA = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'work')); from env_config import env_value  # noqa: E402
API = 'https://appeears.earthdatacloud.nasa.gov/api/'; OUT = ROOT / 'runtime/kma/modis_appeears'; STATE = OUT / 'task.json'
LAYERS = [{'product': 'MOD11A1.061', 'layer': 'LST_Day_1km'}, {'product': 'MOD11A1.061', 'layer': 'LST_Night_1km'}, {'product': 'MCD43A3.061', 'layer': 'Albedo_WSA_shortwave'},
          {'product': 'MOD13A2.061', 'layer': '_1_km_16_days_NDVI'}, {'product': 'MOD13A2.061', 'layer': '_1_km_16_days_EVI'}]


def call(path, token=None, data=None, auth=None, raw=False):
    headers = {'User-Agent': 'Halla-GeoData/1.0'}
    if token: headers['Authorization'] = 'Bearer ' + token
    if auth: headers['Authorization'] = 'Basic ' + base64.b64encode(auth.encode()).decode(); headers['Content-Length'] = '0'
    if data is not None: headers['Content-Type'] = 'application/json'; data = json.dumps(data).encode()
    req = urllib.request.Request(API + path, headers=headers, data=data if data is not None else (b'' if auth else None))
    with urllib.request.urlopen(req, timeout=120) as r: return r.read() if raw else json.loads(r.read())


def main(argv):
    u, pw = env_value('EARTHDATA_USER'), env_value('EARTHDATA_PASS')
    if not (u and pw): print('EARTHDATA_USER / EARTHDATA_PASS가 비어 있습니다. https://urs.earthdata.nasa.gov 에서 계정을 만들고 .env에 적으세요.'); return 2
    args = dict(zip(argv[::2], argv[1::2])); start = args.get('--start', '2023-01-01'); OUT.mkdir(parents=True, exist_ok=True)
    token = call('login', auth=f'{u}:{pw}')['token']
    state = json.loads(STATE.read_text('utf-8')) if STATE.exists() else {}
    if not state.get('task_id'):
        with (GDA / 'data/kma_stations_jeju.csv').open(encoding='utf-8-sig') as f: stations = list(csv.DictReader(f))
        coords = [{'id': s['stn'], 'category': s['name'], 'latitude': float(s['lat']), 'longitude': float(s['lon'])} for s in stations]
        task = {'task_type': 'point', 'task_name': 'halla_geodata_stations', 'params': {'dates': [{'startDate': dt.date.fromisoformat(start).strftime('%m-%d-%Y'), 'endDate': (dt.date.today() - dt.timedelta(days=1)).strftime('%m-%d-%Y')}], 'layers': LAYERS, 'coordinates': coords}}
        res = call('task', token, task); state = {'task_id': res['task_id'], 'submitted': dt.datetime.now().isoformat()}; STATE.write_text(json.dumps(state), encoding='utf-8'); print('submitted task', res['task_id'])
    tid = state['task_id']
    while True:
        st = call(f'status/{tid}', token); status = st.get('status') or st.get('state'); print('status', status, st.get('progress', {}).get('summary', ''))
        if status == 'done': break
        if '--poll' not in argv: print('작업이 아직 처리 중입니다. 나중에 같은 명령을 다시 실행하면 결과를 내려받습니다.'); return 0
        time.sleep(60)
    files = call(f'bundle/{tid}', token)['files']
    for f in files:
        if f['file_name'].endswith('.csv') or f['file_name'].endswith('.json'):
            data = call(f'bundle/{tid}/{f["file_id"]}', token, raw=True); (OUT / Path(f['file_name']).name).write_bytes(data); print('saved', f['file_name'], len(data))
    print('MODIS_APPEEARS_DONE', {'task': tid, 'files': len(files)})


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
