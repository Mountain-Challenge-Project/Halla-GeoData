"""FALLBACK (차선) source, second to 환경부 토지피복도 / 산림청 임상도. Per-cell land-cover and canopy-height factors from the public 10 m rasters (QGIS Python; run from this folder).

Inputs (runtime/external/, downloaded by the stage-6 fetch, manifest in data/external_rasters_manifest.json)
  ESA_WorldCover_10m_2021_v200_N33E126_Map.tif   classes 10 tree, 20 shrub, 30 grass, 40 crop, 50 built-up, 60 bare,
                                                 70 snow/ice, 80 water, 90 wetland, 95 mangrove, 100 moss/lichen
  ETH_GlobalCanopyHeight_10m_2020_N33E126_Map.tif canopy height m (255 = nodata)
For every 500 m cell the class shares (%) inside the cell polygon and the mean / 90th-percentile canopy height are
computed by sampling the rasters on a 50 m lattice inside the cell (about 100 samples). Writes
Geo Data Analyst/data/jeju_grid_landcover.csv; work/update_grid_properties.py joins lc_tree, lc_grass, lc_crop,
lc_builtup, lc_bare, lc_water, canopy_mean_m into grid.geojson. Stations get the same values from their cell.
"""
import os, csv, json, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import numpy as np
from osgeo import gdal, osr
gdal.UseExceptions()
ROOT = Path(__file__).resolve().parents[2]; GDA = ROOT / 'Geo Data Analyst'
LC = ROOT / 'runtime/external/ESA_WorldCover_10m_2021_v200_N33E126_Map.tif'; CH = ROOT / 'runtime/external/ETH_GlobalCanopyHeight_10m_2020_N33E126_Map.tif'
CLASSES = {10: 'tree', 20: 'shrub', 30: 'grass', 40: 'crop', 50: 'builtup', 60: 'bare', 70: 'snow', 80: 'water', 90: 'wetland', 95: 'mangrove', 100: 'moss'}


def opener(path):
    ds = gdal.Open(str(path)); gt = ds.GetGeoTransform(); b = ds.GetRasterBand(1); nd = b.GetNoDataValue()
    # both tiles are EPSG:4326 10 m (~1/12000 deg); read the Jeju window only
    x0 = int((126.05 - gt[0]) / gt[1]); x1 = int((127.05 - gt[0]) / gt[1]); y0 = int((33.65 - gt[3]) / gt[5]); y1 = int((33.05 - gt[3]) / gt[5])
    arr = b.ReadAsArray(x0, y0, x1 - x0, y1 - y0); gt2 = (gt[0] + x0 * gt[1], gt[1], 0, gt[3] + y0 * gt[5], 0, gt[5])
    return arr, gt2, nd


lc, lgt, lnd = opener(LC); ch, cgt, cnd = opener(CH)
print('windows', lc.shape, ch.shape)


def sample(arr, gt, lons, lats):
    c = np.floor((lons - gt[0]) / gt[1]).astype(int); r = np.floor((lats - gt[3]) / gt[5]).astype(int)
    ok = (c >= 0) & (c < arr.shape[1]) & (r >= 0) & (r < arr.shape[0]); out = np.full(lons.shape, -1, 'int32'); out[ok] = arr[r[ok], c[ok]]; return out


grid = json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8'))
rows = []
for f in grid['features']:
    p = f['properties']; ring = np.array(f['geometry']['coordinates'][0]); lon0, lat0, lon1, lat1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
    xs = np.linspace(lon0, lon1, 11)[:-1] + (lon1 - lon0) / 20; ys = np.linspace(lat0, lat1, 11)[:-1] + (lat1 - lat0) / 20; gx, gy = np.meshgrid(xs, ys)
    # keep lattice points inside the (slightly rotated) cell polygon
    px, py = gx.ravel(), gy.ravel(); inside = np.ones(px.shape, bool)
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]; x2, y2 = ring[i + 1]; inside &= ((x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)) <= 1e-12
    if inside.sum() < 10: inside[:] = True
    v = sample(lc, lgt, px[inside], py[inside]); n = max(1, (v > 0).sum())
    row = {'grid_id': p['grid_id'], 'n_samples': int((v > 0).sum())}
    for code, name in CLASSES.items(): row[f'lc_{name}'] = round(100.0 * (v == code).sum() / n, 1)
    h = sample(ch, cgt, px[inside], py[inside]).astype(float); h = h[(h >= 0) & (h != (cnd if cnd is not None else 255)) & (h < 200)]
    row['canopy_mean_m'] = round(float(h.mean()), 1) if h.size else ''; row['canopy_p90_m'] = round(float(np.percentile(h, 90)), 1) if h.size else ''
    rows.append(row)
out = GDA / 'data/jeju_grid_landcover.csv'
with out.open('w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
tree = [r['lc_tree'] for r in rows]; can = [r['canopy_mean_m'] for r in rows if r['canopy_mean_m'] != '']
print('LANDCOVER_WRITTEN', json.dumps({'cells': len(rows), 'tree_share_mean_pct': round(sum(tree) / len(tree), 1), 'cells_mostly_tree': sum(1 for t in tree if t >= 50), 'canopy_mean_m_overall': round(sum(can) / len(can), 1),
                                       'builtup_cells_ge50': sum(1 for r in rows if r['lc_builtup'] >= 50)}))
