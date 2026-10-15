"""Search Earth Search (AWS Open Data STAC) for Sentinel-2 L2A scenes over Jeju and save the result.

Run with plain Python (the QGIS Python's OpenSSL build cannot open HTTPS from urllib):
  python work/stac_search_s2.py [--days 90] [--max-cloud 60]
Writes work/.tmp/open_data/stac_s2.json, which work/build_open_data_layers.py reads.
"""
from pathlib import Path
import argparse, datetime as dt, json, urllib.request

ROOT = Path(__file__).resolve().parent.parent
STAC = 'https://earth-search.aws.element84.com/v1/search'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--days', type=int, default=90); ap.add_argument('--max-cloud', type=float, default=60); a = ap.parse_args()
    body = {'collections': ['sentinel-2-l2a'], 'bbox': [126.14, 33.18, 126.98, 33.58],
            'datetime': (dt.date.today() - dt.timedelta(days=a.days)).isoformat() + 'T00:00:00Z/' + dt.date.today().isoformat() + 'T23:59:59Z',
            'limit': 200, 'query': {'eo:cloud_cover': {'lt': a.max_cloud}}, 'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}]}
    req = urllib.request.Request(STAC, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'HallasanTerrainStudy/1.0'})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.load(r)
    out = ROOT / 'work/.tmp/open_data'; out.mkdir(parents=True, exist_ok=True)
    (out / 'stac_s2.json').write_text(json.dumps({'searched_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'request': body, 'features': data.get('features', [])}, ensure_ascii=False), encoding='utf-8')
    print('STAC_SAVED', len(data.get('features', [])), 'scenes ->', out / 'stac_s2.json')


if __name__ == '__main__':
    main()
