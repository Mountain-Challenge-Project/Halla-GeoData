"""Open-data overlays for the Jeju live map (no API key): Sentinel-2 dated true colour / NDVI / snow
mask composite, GLO-30 hillshade, and OSM POI + sac_scale trail-difficulty GeoJSON.

Run with QGIS Python (GDAL with /vsicurl):
  "C:\\Program Files\\QGIS 4.2.0\\bin\\python-qgis.bat" -X utf8 work/build_open_data_layers.py [--days 90] [--max-cloud 60]

Sentinel-2 L2A COGs come from the AWS Open Data registry (sentinel-cogs bucket) found through the
Earth Search STAC API. Jeju is covered by MGRS tiles 52SBB, 52SBC, 52SCB, 52SCC. For each acquisition
date the four tiles are mosaicked onto a 40 m UTM 52N grid, cloud/shadow pixels are masked with the
SCL band (classes 0,1,3,8,9,10 invalid), and dates are stacked newest-clear-first so the composite
shows the most recent clear pixel; the per-pixel date share is recorded in s2_meta.json.
Reflectance = DN / 10000 (the sentinel-cogs COGs carry no BOA offset; checked on water and vegetation DNs).
Outputs (outputs/jeju_dashboard/data/): s2_truecolor.png, s2_ndvi.png, s2_snow.png, s2_meta.json,
hillshade.png, pois.geojson, sac_scale.geojson. Licences: Copernicus Sentinel data (free and open),
Copernicus DEM (see DATA_SOURCES.md), OpenStreetMap ODbL.
"""
from pathlib import Path
import argparse, datetime as dt, json, math, sys, urllib.request
import numpy as np
from osgeo import gdal, ogr, osr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT

gdal.UseExceptions(); osr.UseExceptions(); ogr.UseExceptions()
gdal.SetConfigOption('GDAL_DISABLE_READDIR_ON_OPEN', 'EMPTY_DIR')
gdal.SetConfigOption('CPL_VSIL_CURL_ALLOWED_EXTENSIONS', '.tif,.TIF')
gdal.SetConfigOption('GDAL_HTTP_MULTIPLEX', 'YES')
# python-qgis.bat does not export the CA bundle that o4w_env.bat sets; without it /vsicurl fails SSL verification.
import os
for ca in [os.environ.get('CURL_CA_BUNDLE', ''), r'C:\Program Files\QGIS 4.2.0\bin\curl-ca-bundle.crt', r'C:\Program Files\QGIS 4.0.3\bin\curl-ca-bundle.crt']:
    if ca and Path(ca).exists():
        gdal.SetConfigOption('CURL_CA_BUNDLE', ca); break
DATA = ROOT / 'outputs/jeju_dashboard/data'
TMP = ROOT / 'work/.tmp/open_data'; TMP.mkdir(parents=True, exist_ok=True)
STAC = 'https://earth-search.aws.element84.com/v1/search'
TILES = {'52SBB', '52SBC', '52SCB', '52SCC'}
RES = 40.0
INVALID_SCL = {0, 1, 3, 8, 9, 10}


def utm_bounds(margin=1500):
    ds = ogr.Open(str(ROOT / 'outputs/jeju_slope/shapefiles/study_boundary.shp')); e = ds.GetLayer(0).GetExtent()
    b = [math.floor((e[0] - margin) / RES) * RES, math.floor((e[2] - margin) / RES) * RES, math.ceil((e[1] + margin) / RES) * RES, math.ceil((e[3] + margin) / RES) * RES]
    return b


def stac_scenes(days, max_cloud):
    # The STAC search is done by work/stac_search_s2.py (plain Python; QGIS Python cannot do HTTPS via urllib).
    cache = TMP / 'stac_s2.json'
    if not cache.exists():
        raise SystemExit('run `python work/stac_search_s2.py` first (saves work/.tmp/open_data/stac_s2.json)')
    feats = json.loads(cache.read_text('utf-8'))['features']
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    feats = [f for f in feats if f['properties']['datetime'][:10] >= cutoff and f['properties'].get('eo:cloud_cover', 100) < max_cloud]
    by_date = {}
    for f in feats:
        tile = (f['properties'].get('grid:code') or '').replace('MGRS-', '')
        if tile not in TILES:
            continue
        day = f['properties']['datetime'][:10]
        by_date.setdefault(day, {})[tile] = f
    return {d: t for d, t in by_date.items() if set(t) == TILES}


def warp_band(urls, bounds, res, resample='bilinear', dtype=gdal.GDT_Float32, nodata=0, tries=4):
    srcs = ['/vsicurl/' + u for u in urls]
    last = None
    for attempt in range(tries):  # remote tile reads occasionally fail mid-stream; retry before giving up on the date
        try:
            ds = gdal.Warp('', srcs, format='MEM', dstSRS='EPSG:32652', outputBounds=bounds, xRes=res, yRes=res, resampleAlg=resample, outputType=dtype, srcNodata=nodata, dstNodata=nodata, multithread=True)
            return ds.ReadAsArray()
        except RuntimeError as e:
            last = e; gdal.VSICurlClearCache(); print('  retry', attempt + 1, 'after', str(e)[:80], flush=True)
    raise last


def read_date(tiles, bounds, day):
    cache = TMP / f's2_{day}_{int(RES)}m.npz'
    if cache.exists():  # per-date mosaics are cached so re-styling does not re-download ~100 MB per date
        z = np.load(cache)
        bands = {k: z[k] for k in ['red', 'green', 'blue', 'nir', 'swir16']}; scl = z['scl']
    else:
        bands = {}
        for key in ['red', 'green', 'blue', 'nir', 'swir16']:
            bands[key] = warp_band([tiles[t]['assets'][key]['href'] for t in sorted(tiles)], bounds, RES)
        scl = warp_band([tiles[t]['assets']['scl']['href'] for t in sorted(tiles)], bounds, RES, resample='near', dtype=gdal.GDT_Byte)
        np.savez_compressed(cache, scl=scl, **bands)
    valid = ~np.isin(scl, list(INVALID_SCL)) & (bands['red'] > 0)
    # sentinel-cogs DNs carry no BOA offset (water red DN ~90, vegetation NDVI median 0.76 at offset 0): reflectance = DN / 10000.
    refl = {k: np.clip(v / 10000.0, 0, 1.2) for k, v in bands.items()}
    return refl, scl, valid


def to_png_rgba(rgba, bounds, name):
    h, w = rgba.shape[1], rgba.shape[2]
    mem = gdal.GetDriverByName('MEM').Create('', w, h, 4, gdal.GDT_Byte)
    mem.SetGeoTransform((bounds[0], RES, 0, bounds[3], 0, -RES)); s = osr.SpatialReference(); s.ImportFromEPSG(32652); mem.SetProjection(s.ExportToWkt())
    for i in range(4):
        mem.GetRasterBand(i + 1).WriteArray(rgba[i])
    warped = gdal.Warp('', mem, format='MEM', dstSRS='EPSG:3857', resampleAlg='bilinear')
    gdal.Translate(str(DATA / name), warped, format='PNG', creationOptions=['ZLEVEL=9'])
    for p in DATA.glob(name + '.aux.xml'):
        p.unlink()
    gt = warped.GetGeoTransform(); W, H = warped.RasterXSize, warped.RasterYSize
    b = [gt[0], gt[3] + gt[5] * H, gt[0] + gt[1] * W, gt[3]]
    ll = lambda x, y: [round(math.degrees(math.atan(math.sinh(y / 6378137.0))), 6), round(math.degrees(x / 6378137.0), 6)]
    return {'epsg3857': b, 'sw': ll(b[0], b[1]), 'ne': ll(b[2], b[3]), 'pixels': [W, H]}


def stretch(x, mask, p_lo=2, p_hi=98, gamma=0.9):
    """Per-band percentile stretch over the valid land pixels (natural-colour look for dark autumn vegetation)."""
    sample = x[mask] if mask.any() else x.ravel()
    lo, hi = np.percentile(sample, p_lo), np.percentile(sample, p_hi)
    if hi <= lo:
        lo, hi = 0.0, 0.3
    y = np.clip((x - lo) / (hi - lo), 0, 1) ** gamma
    return (y * 255).astype(np.uint8)


def ndvi_colour(v):
    """brown (-0.2) -> yellow (0.2) -> green (0.8)."""
    stops = [(-0.2, (140, 94, 50)), (0.1, (214, 180, 110)), (0.3, (235, 226, 120)), (0.5, (120, 190, 80)), (0.7, (30, 140, 50)), (0.9, (5, 80, 30))]
    r = np.zeros(v.shape, np.uint8); g = np.zeros_like(r); b = np.zeros_like(r)
    for (v0, c0), (v1, c1) in zip(stops[:-1], stops[1:]):
        m = (v >= v0) & (v < v1) if v1 < 0.9 else (v >= v0)
        t = np.clip((v - v0) / (v1 - v0), 0, 1)
        for arr, i in ((r, 0), (g, 1), (b, 2)):
            arr[m] = (c0[i] + (c1[i] - c0[i]) * t[m]).astype(np.uint8)
    low = v < -0.2
    r[low], g[low], b[low] = 140, 94, 50
    return r, g, b


def sentinel2(days, max_cloud):
    bounds = utm_bounds()
    scenes = stac_scenes(days, max_cloud)
    dates = sorted(scenes, reverse=True)
    if not dates:
        raise SystemExit('no Sentinel-2 date covers all four Jeju tiles in the window')
    comp = {k: None for k in ['red', 'green', 'blue', 'nir', 'swir16']}; filled = None; date_idx = None; used = []; water = None
    skipped = []
    for di, day in enumerate(dates):
        try:
            refl, scl, valid = read_date(scenes[day], bounds, day)
        except RuntimeError as e:
            skipped.append({'date': day, 'error': str(e)[:120]}); print('S2', day, 'skipped:', str(e)[:100], flush=True); continue
        if filled is None:
            filled = np.zeros(valid.shape, bool); date_idx = np.full(valid.shape, -1, np.int16); comp = {k: np.zeros(valid.shape, np.float32) for k in comp}; water = np.zeros(valid.shape, bool)
        take = valid & ~filled
        for k in comp:
            comp[k][take] = refl[k][take]
        water[take] = scl[take] == 6
        date_idx[take] = di; filled |= take
        share = float(take.sum()) / take.size * 100
        used.append({'date': day, 'tiles': {t: {'id': scenes[day][t]['id'], 'cloud_cover_pct': round(scenes[day][t]['properties'].get('eo:cloud_cover', -1), 1)} for t in sorted(scenes[day])}, 'pixel_share_pct': round(share, 2)})
        print('S2', day, 'new clear pixels', f'{share:.1f}%', 'filled total', f'{filled.mean() * 100:.1f}%', flush=True)
        if filled.mean() > 0.995 or di >= 7:
            break
    alpha = (filled * 255).astype(np.uint8)
    land = filled & ~water
    rgb = np.stack([stretch(comp['red'], land), stretch(comp['green'], land), stretch(comp['blue'], land), alpha])
    tc = to_png_rgba(rgb, bounds, 's2_truecolor.png')
    with np.errstate(invalid='ignore', divide='ignore'):
        ndvi = (comp['nir'] - comp['red']) / (comp['nir'] + comp['red'])
        ndsi = (comp['green'] - comp['swir16']) / (comp['green'] + comp['swir16'])
    ndvi = np.nan_to_num(ndvi, nan=-1); ndsi = np.nan_to_num(ndsi, nan=-1)
    r, g, b = ndvi_colour(ndvi)
    nd = to_png_rgba(np.stack([r, g, b, (land * 200).astype(np.uint8)]), bounds, 's2_ndvi.png')
    snow = land & (ndsi > 0.4) & (comp['green'] > 0.11) & (ndvi < 0.1)
    sn = to_png_rgba(np.stack([np.full(snow.shape, 120, np.uint8), np.full(snow.shape, 200, np.uint8), np.full(snow.shape, 255, np.uint8), (snow * 220).astype(np.uint8)]), bounds, 's2_snow.png')
    meta = {'source': 'Copernicus Sentinel-2 L2A COG, AWS Open Data (sentinel-cogs), Earth Search STAC', 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'resolution_m': RES,
            'composite_rule': 'newest clear pixel first; SCL classes 0,1,3,8,9,10 masked; water (SCL 6) transparent in NDVI/snow; true colour = per-band 2-98 % percentile stretch over land, gamma 0.9',
            'snow_rule': 'NDSI > 0.4 and green reflectance > 0.11 and NDVI < 0.1 on land; leftover cloud can still be counted', 'dates_used': used, 'dates_skipped': skipped, 'coverage_pct': round(float(filled.mean()) * 100, 2), 'land_pixels': int(land.sum()), 'water_pixels': int(water.sum()),
            'ndvi_mean_land': round(float(ndvi[land].mean()), 3) if land.any() else None, 'snow_pixels': int(snow.sum()), 'snow_area_km2': round(float(snow.sum()) * RES * RES / 1e6, 3),
            'truecolor': tc, 'ndvi': nd, 'snow': sn, 'licence': 'Contains modified Copernicus Sentinel data ' + str(dt.date.today().year)}
    (DATA / 's2_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print('S2_DONE', json.dumps({k: meta[k] for k in ['coverage_pct', 'ndvi_mean_land', 'snow_area_km2']}), 'dates', [u['date'] for u in used], flush=True)


def hillshade():
    dem = ROOT / 'outputs/jeju_slope/dem_30m.tif'
    hs = gdal.DEMProcessing('', str(dem), 'hillshade', format='MEM', azimuth=315, altitude=45, zFactor=1.0, computeEdges=True)
    arr = hs.ReadAsArray(); nod = hs.GetRasterBand(1).GetNoDataValue()
    alpha = np.where(arr == nod, 0, 255).astype(np.uint8) if nod is not None else np.full(arr.shape, 255, np.uint8)
    gt = hs.GetGeoTransform(); h, w = arr.shape
    mem = gdal.GetDriverByName('MEM').Create('', w, h, 2, gdal.GDT_Byte); mem.SetGeoTransform(gt); mem.SetProjection(hs.GetProjection())
    mem.GetRasterBand(1).WriteArray(arr.astype(np.uint8)); mem.GetRasterBand(2).WriteArray(alpha)
    warped = gdal.Warp('', mem, format='MEM', dstSRS='EPSG:3857', resampleAlg='bilinear')
    gdal.Translate(str(DATA / 'hillshade.png'), warped, format='PNG', creationOptions=['ZLEVEL=9'])
    for p in DATA.glob('hillshade.png.aux.xml'):
        p.unlink()
    g = warped.GetGeoTransform(); W, H = warped.RasterXSize, warped.RasterYSize
    b = [g[0], g[3] + g[5] * H, g[0] + g[1] * W, g[3]]
    ll = lambda x, y: [round(math.degrees(math.atan(math.sinh(y / 6378137.0))), 6), round(math.degrees(x / 6378137.0), 6)]
    ov = json.loads((DATA / 'overlays.json').read_text('utf-8'))
    ov['hillshade_png'] = {'epsg3857': b, 'sw': ll(b[0], b[1]), 'ne': ll(b[2], b[3]), 'pixels': [W, H], 'source': 'Copernicus GLO-30 DSM, GDAL hillshade az 315 alt 45'}
    (DATA / 'overlays.json').write_text(json.dumps(ov, indent=1), encoding='utf-8')
    print('HILLSHADE_DONE', W, H, flush=True)


def osm_layers():
    raw = json.loads((ROOT / 'work/public_sources/osm_pois_sacscale.json').read_text('utf-8'))
    geom = json.loads((ROOT / 'work/public_sources/osm_sacscale_geom.json').read_text('utf-8')) if (ROOT / 'work/public_sources/osm_sacscale_geom.json').exists() else {'elements': []}
    kinds = {'shelter': '대피소', 'toilets': '화장실', 'parking': '주차장', 'information': '안내소', 'defibrillator': 'AED'}
    pois = []
    for e in raw['elements']:
        t = e.get('tags', {})
        if 'sac_scale' in t and e['type'] == 'way':
            continue
        kind = t.get('amenity') or t.get('tourism') or t.get('emergency')
        if kind not in kinds:
            continue
        lon, lat = (e['lon'], e['lat']) if e['type'] == 'node' else (e['center']['lon'], e['center']['lat'])
        pois.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [round(lon, 5), round(lat, 5)]},
                     'properties': {'kind': kind, 'kind_ko': kinds[kind], 'name': t.get('name', ''), 'shelter_type': t.get('shelter_type', ''), 'fee': t.get('fee', ''), 'capacity': t.get('capacity', ''), 'osm': f"{e['type']}/{e['id']}"}})
    sac_feats = []
    for e in geom['elements']:
        t = e.get('tags', {})
        if e['type'] != 'way' or 'geometry' not in e or 'sac_scale' not in t:
            continue
        sac_feats.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [[round(p['lon'], 5), round(p['lat'], 5)] for p in e['geometry']]},
                          'properties': {'sac_scale': t['sac_scale'], 'highway': t.get('highway', ''), 'name': t.get('name', ''), 'trail_visibility': t.get('trail_visibility', ''), 'osm': f"way/{e['id']}"}})
    (DATA / 'pois.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': pois}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (DATA / 'sac_scale.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': sac_feats}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    from collections import Counter
    print('OSM_DONE', dict(Counter(p['properties']['kind'] for p in pois)), 'sac_scale ways', len(sac_feats), dict(Counter(f['properties']['sac_scale'] for f in sac_feats)), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--days', type=int, default=90); ap.add_argument('--max-cloud', type=float, default=60); ap.add_argument('--skip-s2', action='store_true')
    a = ap.parse_args()
    hillshade(); osm_layers()
    if not a.skip_s2:
        sentinel2(a.days, a.max_cloud)
