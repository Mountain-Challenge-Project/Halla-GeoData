"""Stage 1c: static terrain factors per 500 m cell for the local-weather model (QGIS Python).

From outputs/jeju_slope/dem_30m.tif (Copernicus GLO-30, EPSG:32652) and the cell centres in
outputs/jeju_dashboard/data/grid.geojson, computes for every cell

  tpi_1km_m      cell mean elevation minus the mean DSM elevation within a 1 km radius (cold-air pooling, ridges)
  svf            sky-view factor 1 - mean(sin(horizon angle)) over 16 azimuths, rays to 10 km (night cooling, fog)
  coast_km       distance from the cell centre to the nearest sea pixel (DSM <= 0 m or nodata)
  up_max_<dir>   highest DSM elevation along the ray towards each of 16 directions within 25 km (m): the
                 "upstream ridge height" for the wind that blows FROM that direction (foehn / lee depth)
  up_dist_<dir>  distance to that maximum (km)

Writes outputs/jeju_slope/jeju_grid_terrain_factors.csv; work/update_grid_properties.py joins the fields
(except the 32 per-direction columns, which it packs into up_max/up_dist lists) into grid.geojson.
Rays sample the DSM every 100 m (TPI/SVF) or 250 m (upstream) by nearest pixel. Optionally samples the
DSM at inputs/reference/kma_stations_jeju.csv points and writes station dem_m next to the CSV.
"""
import os, csv, json, math, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import numpy as np
from osgeo import gdal, osr
gdal.UseExceptions()

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / 'outputs/jeju_slope/dem_30m.tif'
GRID = ROOT / 'outputs/jeju_dashboard/data/grid.geojson'
OUT = ROOT / 'outputs/jeju_slope/jeju_grid_terrain_factors.csv'
DIRS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

ds = gdal.Open(str(DEM)); gt = ds.GetGeoTransform(); band = ds.GetRasterBand(1)
z = band.ReadAsArray().astype('float32'); nd = band.GetNoDataValue()
sea = np.zeros(z.shape, bool)
if nd is not None: sea |= (z == nd)
sea |= (z <= 0); z = np.where(sea, 0.0, z)
ny, nx = z.shape; px = gt[1]; print('DEM', nx, 'x', ny, 'px', px, 'm')
src = osr.SpatialReference(); src.ImportFromEPSG(4326); src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
dst = osr.SpatialReference(wkt=ds.GetProjection()); dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
tr = osr.CoordinateTransformation(src, dst)


def sample(xs, ys):
    """nearest-pixel DSM values at projected coords; outside the raster -> 0 (sea)."""
    c = np.floor((xs - gt[0]) / gt[1]).astype(int); r = np.floor((ys - gt[3]) / gt[5]).astype(int)
    ok = (c >= 0) & (c < nx) & (r >= 0) & (r < ny)
    out = np.zeros(xs.shape, 'float32'); out[ok] = z[r[ok], c[ok]]
    return out, ok


# distance-to-sea raster (cell centres sampled from it): coarse 150 m grid is enough for a km-scale factor
step = 5
zs = sea[::step, ::step]
from scipy import ndimage  # QGIS ships scipy
dist_px = ndimage.distance_transform_edt(~zs) * px * step
grid = json.loads(GRID.read_text('utf-8'))
az = np.deg2rad(np.arange(0, 360, 22.5))
rows = []
for k, f in enumerate(grid['features']):
    p = f['properties']; ring = f['geometry']['coordinates'][0]
    lon = sum(q[0] for q in ring[:-1]) / (len(ring) - 1); lat = sum(q[1] for q in ring[:-1]) / (len(ring) - 1)
    x0, y0, _ = tr.TransformPoint(lon, lat)
    z0 = p.get('elev_mean') or 0.0
    # TPI: mean within 1 km radius on a 100 m lattice
    g = np.arange(-1000, 1001, 100); gx, gy = np.meshgrid(g, g); m = (gx ** 2 + gy ** 2) <= 1000 ** 2
    zz, ok = sample(x0 + gx[m], y0 + gy[m]); tpi = z0 - float(zz[ok].mean()) if ok.any() else 0.0
    # horizon angles (SVF) to 10 km and upstream maxima to 25 km along 16 rays
    d_svf = np.arange(100, 10001, 100); d_up = np.arange(250, 25001, 250)
    hsum = 0.0; up_max = []; up_dist = []
    for a in az:
        sx, sy = math.sin(a), math.cos(a)
        zs1, _ = sample(x0 + sx * d_svf, y0 + sy * d_svf); ang = np.arctan2(zs1 - z0, d_svf); hsum += math.sin(max(0.0, float(ang.max())))
        zs2, _ = sample(x0 + sx * d_up, y0 + sy * d_up); i = int(zs2.argmax()); up_max.append(round(float(zs2[i]))); up_dist.append(round(float(d_up[i]) / 1000, 2))
    svf = 1 - hsum / len(az)
    ci = int((x0 - gt[0]) / (gt[1] * step)); ri = int((y0 - gt[3]) / (gt[5] * step))
    coast = float(dist_px[min(max(ri, 0), dist_px.shape[0] - 1), min(max(ci, 0), dist_px.shape[1] - 1)]) / 1000
    row = {'grid_id': p['grid_id'], 'tpi_1km_m': round(tpi, 1), 'svf': round(svf, 3), 'coast_km': round(coast, 2)}
    for d, mx, di in zip(DIRS, up_max, up_dist): row[f'up_max_{d}'] = mx; row[f'up_dist_{d}'] = di
    rows.append(row)
    if k % 1000 == 0: print(' cells', k, flush=True)
with OUT.open('w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
tpis = [r['tpi_1km_m'] for r in rows]; svfs = [r['svf'] for r in rows]; coasts = [r['coast_km'] for r in rows]
print('TERRAIN_FACTORS_WRITTEN', json.dumps({'cells': len(rows), 'tpi_range': [min(tpis), max(tpis)], 'svf_range': [min(svfs), max(svfs)], 'coast_km_max': max(coasts),
                                             'up_max_NW_max': max(r['up_max_NW'] for r in rows)}))
# station DSM heights
st = ROOT / 'inputs/reference/kma_stations_jeju.csv'
if st.exists():
    with st.open(encoding='utf-8-sig') as fh: srows = list(csv.DictReader(fh))
    for r in srows:
        x, y, _ = tr.TransformPoint(float(r['lon']), float(r['lat'])); v, ok = sample(np.array([x]), np.array([y])); r['dem_m'] = round(float(v[0]), 1) if ok[0] else ''
    with st.open('w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(srows[0].keys())); w.writeheader(); w.writerows(srows)
    diffs = [abs(float(r['dem_m']) - float(r['ht_m'])) for r in srows if r.get('dem_m') not in ('', None) and r['ht_m']]
    print('STATION_DEM_SAMPLED', json.dumps({'stations': len(srows), 'median_abs_diff_m': round(float(np.median(diffs)), 1), 'max_abs_diff_m': round(max(diffs), 1)}))
