"""Download public sources for the selected region (SLOPE_REGION, default hallasan).

The Copernicus GLO-30 tile N33/E126 covers the whole of Jeju and is shared by every region;
only the Esri World Imagery background export depends on the region bounds. Existing files are reused.
"""
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
import json, hashlib, sys, time
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT, load

cfg = load()
sat = cfg['satellite']
OUT = ROOT / 'work' / 'public_sources'
OUT.mkdir(exist_ok=True)
region = json.loads((ROOT / cfg['region_json']).read_text(encoding='utf-8'))
manifest_path = OUT / 'download_manifest.json'
records = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []


def save_manifest():
    manifest_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')


def fetch(url, name, max_bytes):
    path = OUT / name
    started = time.time()
    if path.exists() and path.stat().st_size > 0:
        if not any(r['file'] == name for r in records):
            records.append({'url': url, 'file': name, 'bytes': path.stat().st_size,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'reused_download': True})
            save_manifest()
        return path
    req = Request(url, headers={'User-Agent': 'HallasanTerrainStudy/1.0 (public data download)'})
    with urlopen(req, timeout=90) as response, path.open('wb') as target:
        count = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > max_bytes:
                raise RuntimeError('Unexpected response size')
            target.write(chunk)
        media = response.headers.get('Content-Type')
    record = {'url': url, 'file': name, 'bytes': path.stat().st_size,
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'content_type': media, 'downloaded_utc': datetime.now(timezone.utc).isoformat()}
    records[:] = [r for r in records if r['file'] != name] + [record]
    save_manifest()
    print(json.dumps({'download': name, 'bytes': count, 'seconds': round(time.time() - started, 2)}), flush=True)
    return path


tile = 'Copernicus_DSM_COG_10_N33_00_E126_00_DEM'
fetch(f'https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif', 'copernicus_N33_E126.tif', 100_000_000)
fetch('https://copernicus-dem-30m.s3.amazonaws.com/readme.html', 'copernicus_readme.html', 1_000_000)
service = 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
fetch(service + '?f=pjson', 'esri_service.json', 2_000_000)
b = region['bounds_by_epsg']['3857']
margin = sat['margin_m']
if sat.get('square', True):
    cx = (b[0] + b[2]) / 2
    cy = (b[1] + b[3]) / 2
    half = max(b[2] - b[0], b[3] - b[1]) / 2 + margin
    bounds = [cx - half, cy - half, cx + half, cy + half]
    size = [sat['max_pixels'], sat['max_pixels']]
else:
    bounds = [b[0] - margin, b[1] - margin, b[2] + margin, b[3] + margin]
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    scale = sat['max_pixels'] / max(w, h)
    size = [round(w * scale), round(h * scale)]
params = {'bbox': ','.join(f'{x:.5f}' for x in bounds), 'bboxSR': 3857, 'imageSR': 3857,
          'size': f'{size[0]},{size[1]}', 'format': 'jpg', 'transparent': 'false', 'f': 'json'}
result_path = fetch(service + '/export?' + urlencode(params), sat['export'], 1_000_000)
export = json.loads(result_path.read_text(encoding='utf-8'))
if 'error' in export:
    raise RuntimeError(json.dumps(export))
fetch(export['href'], sat['jpg'], 50_000_000)
ex = export['extent']
bounds = [ex['xmin'], ex['ymin'], ex['xmax'], ex['ymax']]
(OUT / sat['extent']).write_text(json.dumps({'epsg': 3857, 'bounds': bounds, 'pixels': [export['width'], export['height']]}, indent=2), encoding='utf-8')
save_manifest()
print('DOWNLOADS_COMPLETE', flush=True)
