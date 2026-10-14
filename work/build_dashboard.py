"""Assemble the Jeju live map dashboard from work/dashboard_src.

Writes
  outputs/jeju_dashboard/index.html  full HTML document (GitHub Pages / local http server; polls
                                     ../hallasan_radar_layers_v1/dist/state/latest.json for radar frames)
  <scratch or given dir>/index.html  the same page without the document skeleton, for publishing as a
                                     claude.ai Artifact (its viewer adds the skeleton and the db capability)
Leaflet 1.9.4 CSS (BSD-2-Clause, (c) Vladimir Agafonkin) is inlined; the JS loads from cdnjs.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'work' / 'dashboard_src'
OUT = ROOT / 'outputs' / 'jeju_dashboard'
head = (SRC / 'head.html').read_text('utf-8').replace('/*LEAFLET_CSS*/', (SRC / 'leaflet-1.9.4.min.css').read_text('utf-8'))
body = (SRC / 'body.html').read_text('utf-8')
CDN_JS = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'
OUT.mkdir(parents=True, exist_ok=True)
# Static copy ships Leaflet locally so GitHub Pages / a LAN server work without a CDN; the Artifact copy loads it from cdnjs (CSP allowlist).
import shutil
shutil.copyfile(SRC / 'leaflet-1.9.4.min.js', OUT / 'leaflet-1.9.4.min.js')
full = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        + head + '</head><body>' + body.replace('__LEAFLET_JS__', 'leaflet-1.9.4.min.js') + '</body></html>')
(OUT / 'index.html').write_text(full, encoding='utf-8')
args = [a for a in sys.argv[1:] if not a.startswith('--')]
artifact_dir = Path(args[0]) if args else ROOT / 'work' / '.tmp' / 'jeju_dashboard_artifact'
artifact_dir.mkdir(parents=True, exist_ok=True)
(artifact_dir / 'index.html').write_text(head + body.replace('__LEAFLET_JS__', CDN_JS), encoding='utf-8')
print('DASHBOARD_BUILT', OUT / 'index.html', len(full), 'bytes;', artifact_dir / 'index.html', len(head + body), 'bytes')

# Standalone template: the same document with two markers. The served page fills them in the
# browser (download button); --standalone fills them here. Markers: `/*__EMBED_JSON__*/null`
# becomes the embedded data object and `/*__LEAFLET_JS__*/` the Leaflet source.
leaflet_src = (SRC / 'leaflet-1.9.4.min.js').read_text('utf-8')
assert '</script' not in leaflet_src
# Leaflet is inlined in the template itself, so building the file in the browser needs only the data marker.
template = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            + head + '</head><body>'
            + body.replace('<script src="__LEAFLET_JS__"></script>',
                           '<script>window.__EMBED__=/*__EMBED_JSON__*/null;</script>\n<script>' + leaflet_src + '</script>')
            + '</body></html>')
(OUT / 'standalone.template.html').write_text(template, encoding='utf-8')

if '--standalone' in sys.argv:
    # One self-contained file: Leaflet, all GeoJSON and both images embedded, so it opens from disk
    # (file://) with no server. Not committed; it is 6-7 MB and regenerable.
    import base64, json
    data_dir = OUT / 'data'
    embed = {n: json.loads((data_dir / (n + ('.json' if n == 'overlays' else '.geojson'))).read_text('utf-8'))
             for n in ['overlays', 'olle', 'trails', 'steep', 'boundary', 'park', 'grid']}
    embed['images'] = {'satellite': 'data:image/jpeg;base64,' + base64.b64encode((data_dir / 'satellite.jpg').read_bytes()).decode(),
                       'slope': 'data:image/png;base64,' + base64.b64encode((data_dir / 'slope.png').read_bytes()).decode()}
    frame_path = OUT / 'data' / 'latest_frame.json'
    if frame_path.exists():  # real radar frame produced by work/radar_to_frame.py, embedded with its observation time
        embed['frame'] = json.loads(frame_path.read_text('utf-8'))
    warn_path = OUT / 'data' / 'warnings.json'
    if warn_path.exists():  # KMA warning status from work/fetch_kma_warnings.py
        embed['warnings'] = json.loads(warn_path.read_text('utf-8'))
    payload = json.dumps(embed, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    target = Path(args[1]) if len(args) > 1 else ROOT / 'work' / '.tmp' / 'jeju_live_map_standalone.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    # count=1: the page script itself mentions the marker string in its download routine.
    target.write_text(template.replace('/*__EMBED_JSON__*/null', payload, 1), encoding='utf-8')
    print('STANDALONE_BUILT', target, target.stat().st_size, 'bytes')
