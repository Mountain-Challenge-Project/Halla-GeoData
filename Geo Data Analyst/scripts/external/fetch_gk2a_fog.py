"""천리안 2A (GK2A) Level-2 products over Korea from the KMA API Hub (approved for KMA_API_KEY; no extra key).

Accumulates the current fog (FOG), cloud detection (CLD) and land surface temperature (LST) files for the Korea
region (KO) so the mountain-fog label archive grows from now on; past data need an NMSC application (NMSC_API_KEY,
not used yet). Each run lists the files of the last --hours (default 3) and downloads those not yet present into
runtime/kma/gk2a/<product>/. Files are NetCDF; the cell-level mapping is a later step.
Usage: python fetch_gk2a_fog.py [--hours 3] [--products FOG,CLD,LST]
"""
import json, sys, time, datetime as dt, urllib.request, urllib.parse, urllib.error
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work')); from env_config import env_value  # noqa: E402
API = 'https://apihub.kma.go.kr/api/typ05/api/GK2A/LE2/{prod}/KO/'; OUT = ROOT / 'runtime/kma/gk2a'


def get(url, params, key, timeout=120):
    req = urllib.request.Request(url + '?' + urllib.parse.urlencode({**params, 'authKey': key}), headers={'User-Agent': 'Halla-GeoData/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()


def main(argv):
    key = env_value('KMA_API_KEY')
    if not key: print('KMA_API_KEY가 비어 있습니다.'); return 2
    args = dict(zip(argv[::2], argv[1::2])); hours = int(args.get('--hours', '3')); prods = args.get('--products', 'FOG,CLD,LST').split(',')
    utc = dt.datetime.now(dt.timezone.utc); s = (utc - dt.timedelta(hours=hours)).strftime('%Y%m%d%H%M'); e = utc.strftime('%Y%m%d%H%M')
    summary = {}
    for prod in prods:
        d = OUT / prod; d.mkdir(parents=True, exist_ok=True)
        try: lst = json.loads(get(API.format(prod=prod) + 'dataList', {'sDate': s, 'eDate': e}, key).decode('utf-8', 'replace'))
        except Exception as ex: summary[prod] = f'list error {type(ex).__name__}'; continue
        items = [x['item'] for x in lst.get('list', [])]; n = 0
        for tm in items:
            dest = d / f'gk2a_le2_{prod.lower()}_ko_{tm}.nc'
            if dest.exists() and dest.stat().st_size > 0: continue
            try:
                data = get(API.format(prod=prod) + 'data', {'date': tm}, key, 300)
                if len(data) < 1000: continue
                dest.write_bytes(data); n += 1; time.sleep(0.5)
            except Exception as ex: summary[prod + '_err'] = type(ex).__name__
        summary[prod] = {'listed': len(items), 'downloaded': n}
    print('GK2A_DONE', json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
