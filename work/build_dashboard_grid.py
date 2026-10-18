"""Rebuild the dashboard's static data from the Jeju slope bundle (QGIS Python).

  outputs/jeju_dashboard/data/grid.geojson     cells (WGS84) with grid_id, i_ref, j_ref, zone, land_pct, slope and height statistics,
                                               steep_pct (= share of the cell area at 20 deg or more); aspect / terrain / land-cover
                                               fields are added afterwards by work/update_grid_properties.py
  outputs/jeju_dashboard/data/boundary.geojson union of the land + islet cells (the analysis outline) and, as a second feature,
                                               the union of the whole grid including the 2 km coastal buffer
  outputs/jeju_dashboard/data/satellite.jpg    copy of work/public_sources/satellite_jeju.jpg (Esri export for the region bounds)
  outputs/jeju_dashboard/data/aspect.png       slope-face direction (8 sectors) rendered from aspect_degrees_30m.tif in EPSG:3857
  outputs/jeju_dashboard/data/slope.png        slope classes rendered from outputs/jeju_slope/slope_degrees_30m.tif in EPSG:3857
  outputs/jeju_dashboard/data/overlays.json    image bounds (EPSG:3857 and WGS84) and credits; existing hillshade entry is kept
Run after the SLOPE_REGION=jeju cascade (prepare -> fetch_slope_sources -> build_slope_data -> render).
"""
import os, csv, json, shutil
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import numpy as np
from osgeo import gdal, ogr, osr
gdal.UseExceptions(); ogr.UseExceptions()
ROOT = Path(__file__).resolve().parent.parent
SLOPE = ROOT / 'outputs/jeju_slope'; OUT = ROOT / 'outputs/jeju_dashboard/data'; OUT.mkdir(parents=True, exist_ok=True)
SRC = ROOT / 'work/public_sources'


def srs(code):
    s = osr.SpatialReference(); s.ImportFromEPSG(code); s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER); return s


# cells: shapefile geometry + CSV statistics + zone from the reference gpkg
ref = ogr.Open(str(ROOT / 'inputs/reference/radar_grid_cells.gpkg')); zones = {f.GetField('ref_id'): (f.GetField('zone') or 'land', f.GetField('land_pct')) for f in ref.GetLayerByName('jeju_grid_500m')}
stats = {r['grid_id']: r for r in csv.DictReader((SLOPE / 'jeju_grid_slope.csv').open(encoding='utf-8-sig'))}
shp = ogr.Open(str(SLOPE / 'shapefiles/grid_slope_500m.shp')); ly = shp.GetLayer(); src_srs = ly.GetSpatialRef().Clone(); src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
tr = osr.CoordinateTransformation(src_srs, srs(4326)); feats = []; union_land = ogr.Geometry(ogr.wkbMultiPolygon); union_all = ogr.Geometry(ogr.wkbMultiPolygon)
steep_cols = ['p20_25', 'p25_30', 'p30_35', 'p35_40', 'p40_45', 'p45_plus']
for f in ly:
    gid = f.GetField('grid_id'); r = stats[gid]; g = f.GetGeometryRef().Clone(); union_all.AddGeometry(g.Clone())
    zone, land_pct = zones.get(gid, ('land', None))
    if zone != 'sea_buffer': union_land.AddGeometry(g.Clone())
    g = g.SimplifyPreserveTopology(1.0)   # drop the densified vertices: back to the 4 corners (metres in the source CRS)
    g.Transform(tr); coords = [[round(x, 5), round(y, 5)] for x, y, *_ in g.GetGeometryRef(0).GetPoints()]
    props = {'grid_id': gid, 'i_ref': int(r['i_ref']), 'j_ref': int(r['j_ref']), 'zone': zone, 'land_pct': round(float(land_pct), 1) if land_pct is not None else None,
             'mean_deg': round(float(r['mean_deg']), 6), 'p90_deg': round(float(r['p90_deg']), 6), 'max_deg': round(float(r['max_deg']), 6), 'elev_mean': round(float(r['elev_mean']), 6), 'elev_max': round(float(r['elev_max']), 6),
             'steep_pct': round(sum(float(r[c]) for c in steep_cols), 6)}
    feats.append({'type': 'Feature', 'properties': props, 'geometry': {'type': 'Polygon', 'coordinates': [coords]}})
(OUT / 'grid.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': feats}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def to_feature(geom, name):
    g = geom.UnionCascaded() if geom.GetGeometryCount() > 1 else geom.Clone(); g.Transform(tr); g = g.SimplifyPreserveTopology(0.00005)
    return {'type': 'Feature', 'properties': {'name': name}, 'geometry': json.loads(g.ExportToJson())}


(OUT / 'boundary.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': [to_feature(union_land, 'land_and_islets'), to_feature(union_all, 'grid_with_coastal_buffer')]}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
# satellite background
shutil.copyfile(SRC / 'satellite_jeju.jpg', OUT / 'satellite.jpg'); sat_ext = json.loads((SRC / 'satellite_jeju_extent.json').read_text('utf-8'))
# slope classes in EPSG:3857 over the satellite bounds
b = sat_ext['bounds']; w = sat_ext['pixels'][0]; h = sat_ext['pixels'][1]
slope = gdal.Warp('', str(SLOPE / 'slope_degrees_30m.tif'), format='MEM', dstSRS='EPSG:3857', outputBounds=b, width=w, height=h, resampleAlg='near', dstNodata=-9999)
a = slope.ReadAsArray(); colors = ['ffffff', 'fcffb8', 'fff158', 'ffd800', 'ffab09', 'ff7826', 'f53b22', 'd20000', 'a40000', '7c0014']
rgba = np.zeros((4, a.shape[0], a.shape[1]), np.uint8)
for i, c in enumerate(colors):
    m = (a >= i * 5) & (a < (i + 1) * 5 if i < 9 else a <= 90)
    for k in range(3): rgba[k, m] = int(c[k * 2:k * 2 + 2], 16)
    rgba[3, m] = 180
rgba[3, a < 0.5] = 0   # sea / flat water transparent
drv = gdal.GetDriverByName('MEM'); ds = drv.Create('', a.shape[1], a.shape[0], 4, gdal.GDT_Byte); ds.SetGeoTransform(slope.GetGeoTransform()); ds.SetProjection(slope.GetProjection())
for k in range(4): ds.GetRasterBand(k + 1).WriteArray(rgba[k])
gdal.Translate(str(OUT / 'slope.png'), ds, format='PNG')
# aspect (slope face direction) in 8 sectors, same bounds; flat (slope < 2 deg) and sea transparent
aspect = gdal.Warp('', str(SLOPE / 'aspect_degrees_30m.tif'), format='MEM', dstSRS='EPSG:3857', outputBounds=b, width=w, height=h, resampleAlg='near', dstNodata=-9999)
asp = aspect.ReadAsArray(); ASPECT_COLORS = ['d7191c', 'fdae61', 'ffffbf', 'a6d96a', '1a9641', '2b83ba', '5e3c99', 'b2abd2']   # N NE E SE S SW W NW
sector = ((np.mod(asp + 22.5, 360) // 45).astype(int)) % 8
rgba2 = np.zeros((4, a.shape[0], a.shape[1]), np.uint8)
for i, c in enumerate(ASPECT_COLORS):
    m = (sector == i) & (asp >= 0) & (a >= 2)
    for k in range(3): rgba2[k, m] = int(c[k * 2:k * 2 + 2], 16)
    rgba2[3, m] = 190
ds2 = drv.Create('', a.shape[1], a.shape[0], 4, gdal.GDT_Byte); ds2.SetGeoTransform(slope.GetGeoTransform()); ds2.SetProjection(slope.GetProjection())
for k in range(4): ds2.GetRasterBand(k + 1).WriteArray(rgba2[k])
gdal.Translate(str(OUT / 'aspect.png'), ds2, format='PNG')
wgs = osr.CoordinateTransformation(srs(3857), srs(4326)); sw = wgs.TransformPoint(b[0], b[1]); ne = wgs.TransformPoint(b[2], b[3])
ov_path = OUT / 'overlays.json'; ov = json.loads(ov_path.read_text('utf-8')) if ov_path.exists() else {}
ov['slope_png'] = {'epsg3857': b, 'sw': [round(sw[1], 6), round(sw[0], 6)], 'ne': [round(ne[1], 6), round(ne[0], 6)], 'pixels': [w, h]}
ov['aspect_png'] = {'epsg3857': b, 'sw': [round(sw[1], 6), round(sw[0], 6)], 'ne': [round(ne[1], 6), round(ne[0], 6)], 'pixels': [w, h], 'sectors': ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'], 'colors': ['#' + c for c in ASPECT_COLORS], 'note': 'GDAL Horn aspect of the 30 m DSM; flat (< 2 deg) and sea transparent'}
ov['satellite_jpg'] = {'epsg3857': b, 'sw': [round(sw[1], 6), round(sw[0], 6)], 'ne': [round(ne[1], 6), round(ne[0], 6)]}
ov.setdefault('credits', {'terrain': 'produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.', 'imagery': 'Esri, Vantor, Earthstar Geographics, GIS User Community', 'vectors': '(c) OpenStreetMap contributors, ODbL; Natural Earth'})
ov['grid'] = {'cells': len(feats), 'zones': {z: sum(1 for f in feats if f['properties']['zone'] == z) for z in ('land', 'islet', 'sea_buffer')}, 'coastal_buffer_m': 2000}
ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=1), encoding='utf-8')
print('DASHBOARD_GRID_BUILT', json.dumps({'cells': len(feats), 'zones': ov['grid']['zones'], 'satellite_px': [w, h], 'bounds_wgs': [ov['slope_png']['sw'], ov['slope_png']['ne']]}))
