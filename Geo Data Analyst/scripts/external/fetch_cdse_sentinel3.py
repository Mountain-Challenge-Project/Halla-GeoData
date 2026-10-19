"""Sentinel-3 SLSTR Level-2 land surface temperature (SL_2_LST) over Jeju from the Copernicus Data Space Ecosystem.

Needs CDSE_CLIENT_ID / CDSE_CLIENT_SECRET in .env (OAuth client created in the CDSE account settings). Searches the
STAC catalogue for SL_2_LST products intersecting the Jeju box between --start and --end (default: last 30 days),
downloads each product ZIP through the OData download endpoint into runtime/kma/sentinel3_lst/ and writes a manifest.
Processing to the 500 m cells (cloud mask, reprojection) is a later step; this script only secures the originals.
"""
import json, sys, time, datetime as dt, urllib.request, urllib.parse, urllib.error
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work')); from env_config import env_value  # noqa: E402
OUT = ROOT / 'runtime/kma/sentinel3_lst'; BBOX = '126.0,33.0,127.1,33.7'
TOKEN_URL = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
STAC = 'https://catalogue.dataspace.copernicus.eu/stac/search'; ODATA = 'https://download.dataspace.copernicus.eu/odata/v1/Products({id})/$value'


def token(cid, cs):
    data = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': cid, 'client_secret': cs}).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}), timeout=60) as r: return json.loads(r.read())['access_token']


def main(argv):
    cid, cs = env_value('CDSE_CLIENT_ID'), env_value('CDSE_CLIENT_SECRET')
    if not (cid and cs): print('CDSE_CLIENT_ID / CDSE_CLIENT_SECRET가 비어 있습니다. https://dataspace.copernicus.eu 계정 설정에서 OAuth 클라이언트를 만들어 .env에 적으세요.'); return 2
    args = dict(zip(argv[::2], argv[1::2])); end = args.get('--end', dt.date.today().isoformat()); start = args.get('--start', (dt.date.today() - dt.timedelta(days=30)).isoformat())
    OUT.mkdir(parents=True, exist_ok=True); tok = token(cid, cs)
    body = json.dumps({'collections': ['SENTINEL-3'], 'bbox': [float(x) for x in BBOX.split(',')], 'datetime': f'{start}T00:00:00Z/{end}T23:59:59Z', 'limit': 100, 'filter': {'op': '=', 'args': [{'property': 'productType'}, 'SL_2_LST___']}, 'filter-lang': 'cql2-json'}).encode()
    with urllib.request.urlopen(urllib.request.Request(STAC, data=body, headers={'Content-Type': 'application/json'}), timeout=120) as r: items = json.loads(r.read()).get('features', [])
    man_path = OUT / 'manifest.json'; man = json.loads(man_path.read_text('utf-8')) if man_path.exists() else {}
    n = 0
    for it in items:
        pid = it['id']; name = it.get('properties', {}).get('title') or pid
        if pid in man: continue
        url = ODATA.format(id=pid); dest = OUT / (name + '.zip')
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + tok})
        with urllib.request.urlopen(req, timeout=600) as r, dest.open('wb') as f:
            while True:
                b = r.read(1 << 20)
                if not b: break
                f.write(b)
        man[pid] = {'file': dest.name, 'datetime': it['properties'].get('datetime'), 'bytes': dest.stat().st_size, 'downloaded_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
        man_path.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding='utf-8'); n += 1; print('downloaded', dest.name, dest.stat().st_size); time.sleep(1)
    print('SENTINEL3_LST_DONE', {'found': len(items), 'new': n, 'window': [start, end]})


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
