"""Status of every external credential slot in .env and whether its service answers (never prints a key).

  python "Geo Data Analyst/scripts/external/check_external_keys.py"

For each source: slot present / filled, a light reachability test (unauthenticated or token-only), the fetch script
that uses it, and the data it unlocks. Writes Geo Data Analyst/data/external_keys_status.json (booleans only).
"""
import json, sys, datetime as dt, urllib.request, urllib.error, urllib.parse, base64
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work')); from env_config import env_value  # noqa: E402


def http(url, headers=None, data=None, timeout=30):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Halla-GeoData/1.0', **(headers or {})}, data=data)
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read(300)
    except urllib.error.HTTPError as e: return e.code, e.read(300)
    except Exception as e: return None, str(e)[:80].encode()


checks = []
# KMA API Hub
k = env_value('KMA_API_KEY'); st, body = http(f'https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtNcst?pageNo=1&numOfRows=1&dataType=JSON&base_date={dt.datetime.now().strftime("%Y%m%d")}&base_time=0600&nx=54&ny=36&authKey={k}') if k else (None, b'')
checks.append({'source': '기상청 API허브', 'env': 'KMA_API_KEY', 'filled': bool(k), 'reachable': st == 200 and b'"resultCode":"00"' in body, 'script': 'work/fetch_kma_*.py, Geo Data Analyst/scripts/*.py', 'unlocks': '관측·예보·레이더·KIM·특보 (필수)'})
# CDS
k = env_value('CDS_API_KEY'); st, body = http('https://cds.climate.copernicus.eu/api/profiles/v1/account/verification/pat', headers={'PRIVATE-TOKEN': k}) if k else (None, b'')
checks.append({'source': 'Copernicus CDS (ERA5 원자료, 1순위)', 'env': 'CDS_API_KEY', 'filled': bool(k), 'reachable': st == 200, 'script': 'external/fetch_cds_era5.py', 'unlocks': 'ERA5-Land·ERA5 등압면 NetCDF (Open-Meteo 차선 자료 대체)'})
# Earthdata
u, pw = env_value('EARTHDATA_USER'), env_value('EARTHDATA_PASS')
st = None
if u and pw:
    st, body = http('https://appeears.earthdatacloud.nasa.gov/api/login', headers={'Authorization': 'Basic ' + base64.b64encode(f'{u}:{pw}'.encode()).decode(), 'Content-Length': '0'}, data=b'')
checks.append({'source': 'NASA Earthdata / AppEEARS (MODIS)', 'env': 'EARTHDATA_USER, EARTHDATA_PASS', 'filled': bool(u and pw), 'reachable': st == 200, 'script': 'external/fetch_earthdata_modis.py', 'unlocks': 'MOD07 기온·수증기 프로파일, MOD11 LST, MCD43 알베도 (지점 시계열 CSV)'})
# CDSE
cid, cs = env_value('CDSE_CLIENT_ID'), env_value('CDSE_CLIENT_SECRET'); st = None
if cid and cs:
    st, body = http('https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token', headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': cid, 'client_secret': cs}).encode())
checks.append({'source': 'Copernicus Data Space (Sentinel-3 SLSTR)', 'env': 'CDSE_CLIENT_ID, CDSE_CLIENT_SECRET', 'filled': bool(cid and cs), 'reachable': st == 200, 'script': 'external/fetch_cdse_sentinel3.py', 'unlocks': 'SL_2_LST 지표면온도 (1 km)'})
# data.go.kr
k = env_value('DATA_GO_KR_KEY')
checks.append({'source': '공공데이터포털 (환경부·산림청 Open API)', 'env': 'DATA_GO_KR_KEY', 'filled': bool(k), 'reachable': None, 'script': '(보조) external/import_me_landcover_shp.py 안내 참조', 'unlocks': '토지피복·임상도 조회 API (전역 SHP는 포털 다운로드가 빠름)'})
# NMSC
k = env_value('NMSC_API_KEY')
checks.append({'source': '국가기상위성센터 (천리안 과거)', 'env': 'NMSC_API_KEY', 'filled': bool(k), 'reachable': None, 'script': 'external/fetch_gk2a_fog.py (현재분은 API허브 키로 동작)', 'unlocks': '천리안 2A 안개·구름 과거 산출물'})
# local SHP paths
for env, name, script in [('ME_LANDCOVER_SHP', '환경부 세분류 토지피복도 SHP', 'external/import_me_landcover_shp.py'), ('FGIS_FOREST_SHP', '산림청 임상도 SHP', 'external/import_fgis_forest_shp.py')]:
    p = env_value(env); ok = bool(p) and Path(p).exists()
    checks.append({'source': name, 'env': env, 'filled': bool(p), 'reachable': ok if p else None, 'script': script, 'unlocks': '셀별 토지피복 비율 / 임상·영급 (WorldCover·ETH 차선 자료 대체)'})
out = {'checked_at': dt.datetime.now().isoformat(timespec='minutes'), 'checks': checks}
(ROOT / 'Geo Data Analyst/data/external_keys_status.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
for c in checks:
    print(f"{'OK  ' if c['reachable'] else ('SET ' if c['filled'] else '--  ')} {c['source']:<42} env={c['env']:<36} {'동작' if c['reachable'] else ('입력됨·미확인' if c['filled'] else '비어 있음')}")
