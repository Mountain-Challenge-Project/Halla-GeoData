"""Download Jeju Olle (제주올레) routes from OpenStreetMap through the Overpass API.

Run with a plain Python (the QGIS Python's OpenSSL build cannot open HTTPS from urllib).
Three requests, each retried across public mirrors:
  1. tag listing of walking/hiking route relations on Jeju, filtered locally for Olle names;
  2. full geometry of the selected relations (osm_olle_relations.json);
  3. highway ways whose name mentions 올레, for courses that OSM maps without a relation
     (osm_olle_ways.json).
Raw responses are stored under work/public_sources and recorded in download_manifest.json.
© OpenStreetMap contributors, ODbL 1.0. OSM coverage of the official courses is not complete.
"""
from pathlib import Path
import hashlib, json, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT

OUT = ROOT / 'work' / 'public_sources'
BBOX = '33.1,126.1,33.6,127.0'
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
           'https://overpass.private.coffee/api/interpreter', 'https://z.overpass-api.de/api/interpreter']
OLLE = re.compile(r'올레|olle|^JOT', re.I)
manifest_path = OUT / 'download_manifest.json'
records = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []


def query(text, timeout=240):
    last = None
    for host in MIRRORS:
        req = urllib.request.Request(host + '?' + urllib.parse.urlencode({'data': text}),
                                     headers={'User-Agent': 'HallasanTerrainStudy/1.0 (public data download)'})
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            json.loads(data)  # reject HTML error pages
            print(json.dumps({'mirror': host, 'bytes': len(data), 'seconds': round(time.time() - started, 1)}), flush=True)
            return host, data
        except Exception as exc:  # try the next mirror
            last = exc
            print('mirror failed:', host, type(exc).__name__, flush=True)
    raise SystemExit('all Overpass mirrors failed: ' + repr(last))


def store(name, host, text, raw):
    target = OUT / name
    target.write_bytes(raw)
    records[:] = [r for r in records if r['file'] != name]
    records.append({'url': host, 'overpass_ql': text, 'file': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                    'content_type': 'application/json', 'downloaded_utc': datetime.now(timezone.utc).isoformat(),
                    'licence': 'ODbL 1.0, © OpenStreetMap contributors'})
    manifest_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    return target


def is_olle(tags):
    return any(OLLE.search(str(v)) for k, v in tags.items() if k in ('name', 'name:ko', 'name:en', 'ref', 'network:name', 'description', 'official_name'))


listing = f'[out:json][timeout:180];(relation["route"~"^(hiking|foot|walking)$"]({BBOX});relation["network"~"^(iwn|nwn|rwn|lwn)$"]({BBOX});relation["type"="superroute"]({BBOX}););out tags;'
host, raw = query(listing)
elements = json.loads(raw)['elements']
selected = sorted({e['id'] for e in elements if is_olle(e.get('tags', {}))})
print('route relations in bbox:', len(elements), '| Olle-tagged:', len(selected), flush=True)
if not selected:
    raise SystemExit('no Olle relations found')

geometry = f'[out:json][timeout:240];relation(id:{",".join(map(str, selected))});out geom;'
host2, raw2 = query(geometry, timeout=300)
rel_file = store('osm_olle_relations.json', host2, geometry, raw2)
for e in sorted(json.loads(raw2)['elements'], key=lambda e: (e['tags'].get('ref', '').zfill(6), e['tags'].get('name', ''))):
    t = e['tags']
    ways = sum(1 for m in e.get('members', []) if m['type'] == 'way' and m.get('geometry'))
    print(e['id'], '|', t.get('ref', ''), '|', t.get('name', ''), '|', t.get('network', ''), '| ways with geometry', ways)

ways_query = f'[out:json][timeout:240];way["highway"]["name"~"올레"]({BBOX});out geom;'
host3, raw3 = query(ways_query, timeout=300)
way_file = store('osm_olle_ways.json', host3, ways_query, raw3)
print('named Olle ways:', len(json.loads(raw3)['elements']))
print('OLLE_DOWNLOAD_COMPLETE', rel_file.name, way_file.name, flush=True)
