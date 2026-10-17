"""Build the 500 m reference grids in the OFFICIAL KMA radar-composite grid definition.

Verified 2026-10-15 against nph-rdr_latlon_api (work/public_sources/kma_radar_grid.json): Lambert
conformal conic, standard parallels 30/60, origin 126E/38N, WGS84 ellipsoid; cell (i, j) centre at
((i-1121)*500, (j-1681)*500) m; 1-based numbering of the 2305 x 2881 HB composite (max error 0.78 m).
Cell ids keep the I%04dJ%04d form so they match radar cell numbers exactly.

Writes inputs/reference/radar_grid_cells.gpkg with
  hallasan_grid_500m   the 43 x 43 block i 1202-1244, j 651-693 (1,849 cells; same ids as before)
  jeju_grid_500m       every cell with GLO-30 land (>= 5 DSM pixels above 0.5 m, from the full 1-degree tile, so 우도·마라도·
                       가파도·비양도·지귀도 are included) or touching the Natural Earth outline, plus the sea cells within
                       COAST_BUFFER_M (2 km) of a land cell. Field zone = land | islet | sea_buffer, land_pct from the DSM.
  jeju_outline         the outline reprojected into the official CRS
  grid_definition      one row with the CRS proj4, numbering and verification summary
The earlier grids (candidate_lcc_grid_500m in hallasan_course_cells.gpkg, jeju_grid_cells.gpkg) used a
spherical LCC and sit about 1.06 km south of these cells at Jeju.
"""
from pathlib import Path
import json, math, sys
from osgeo import ogr, osr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT

ogr.UseExceptions(); osr.UseExceptions()
I0, J0, SIZE = 1121, 1681, 500
HALLASAN = (range(1202, 1245), range(651, 694))
GRID_DEF = json.loads((ROOT / 'work/public_sources/kma_radar_grid.json').read_text('utf-8'))
PROJ4 = GRID_DEF['official_crs_proj4']
SOURCE = 'KMA 레이더 합성(HB) 500m 격자 정의 · nph-rdr_latlon_api(cmp=PCP) 경위도로 2026-10-15 검증 · 제주 외곽선: Natural Earth 1:10m (public domain)'
NOTICE = ('공식 레이더 격자: LCC 표준위선 30/60, 원점 126E/38N, WGS84 타원체, 기준셀 중심 i0=1121,j0=1681, 500 m. '
          '셀 ID는 레이더 격자 번호와 같음(전국 격자 최대 오차 0.78 m). 실제 API 수신 강수는 별도 프레임 파일에 있음.')

srs = osr.SpatialReference(); srs.ImportFromProj4(PROJ4); srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
src = ogr.Open(str(ROOT / 'inputs/reference/hallasan_course_cells.gpkg'), 0)
outline_layer = src.GetLayerByName('jeju_outline'); outline_feature = next(iter(outline_layer))
outline = outline_feature.GetGeometryRef().Clone()
old_srs = outline_layer.GetSpatialRef().Clone(); old_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
outline.Segmentize(200); outline.Transform(osr.CoordinateTransformation(old_srs, srs))


def square(ci, cj):
    x0 = (ci - I0) * SIZE - SIZE / 2; y0 = (cj - J0) * SIZE - SIZE / 2
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in [(x0, y0), (x0 + SIZE, y0), (x0 + SIZE, y0 + SIZE), (x0, y0 + SIZE), (x0, y0)]:
        ring.AddPoint_2D(x, y)
    poly = ogr.Geometry(ogr.wkbPolygon); poly.AddGeometry(ring); return poly


FIELDS = [('ref_id', ogr.OFTString), ('i_cell', ogr.OFTInteger), ('j_cell', ogr.OFTInteger), ('center_x_m', ogr.OFTReal), ('center_y_m', ogr.OFTReal),
          ('size_m', ogr.OFTInteger), ('area_m2', ogr.OFTReal), ('land_pct', ogr.OFTReal), ('in_hallasan', ogr.OFTInteger), ('zone', ogr.OFTString), ('source', ogr.OFTString), ('notice', ogr.OFTString)]


def write_layer(ds, name, cells):
    layer = ds.CreateLayer(name, srs, ogr.wkbPolygon)
    for n, k in FIELDS:
        layer.CreateField(ogr.FieldDefn(n, k))
    for cell in cells:
        ci, cj, poly, land, in_h = cell[:5]; zn = cell[5] if len(cell) > 5 else 'land'
        f = ogr.Feature(layer.GetLayerDefn()); f.SetGeometry(poly)
        for k, v in {'ref_id': f'I{ci:04d}J{cj:04d}', 'i_cell': ci, 'j_cell': cj, 'center_x_m': (ci - I0) * SIZE, 'center_y_m': (cj - J0) * SIZE, 'size_m': SIZE,
                     'area_m2': SIZE * SIZE, 'land_pct': land, 'in_hallasan': in_h, 'zone': zn, 'source': SOURCE, 'notice': NOTICE}.items():
            f.SetField(k, v)
        layer.CreateFeature(f)
    return layer


COAST_BUFFER_M = 2000
import numpy as np
from osgeo import gdal
gdal.UseExceptions()
_dem = gdal.Open(str(ROOT / 'work/public_sources/copernicus_N33_E126.tif')); _gt = _dem.GetGeoTransform(); _z = _dem.GetRasterBand(1).ReadAsArray()
_wgs = osr.SpatialReference(); _wgs.ImportFromEPSG(4326); _wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
_to_wgs = osr.CoordinateTransformation(srs, _wgs)


def land_share(ci, cj):
    """share (0-100) of a 50 m lattice inside cell (ci, cj) whose GLO-30 height is above 0.5 m (sea = 0)."""
    x0 = (ci - I0) * SIZE - SIZE / 2; y0 = (cj - J0) * SIZE - SIZE / 2
    g = np.arange(25, SIZE, 50); gx, gy = np.meshgrid(x0 + g, y0 + g)
    pts = _to_wgs.TransformPoints([(float(x), float(y)) for x, y in zip(gx.ravel(), gy.ravel())])
    lon = np.array([q[0] for q in pts]); lat = np.array([q[1] for q in pts])
    c = ((lon - _gt[0]) / _gt[1]).astype(int); r = ((lat - _gt[3]) / _gt[5]).astype(int)
    ok = (c >= 0) & (c < _z.shape[1]) & (r >= 0) & (r < _z.shape[0])
    if not ok.any(): return 0.0
    return float((_z[r[ok], c[ok]] > 0.5).sum()) / ok.sum() * 100


hallasan = []
for cj in HALLASAN[1]:
    for ci in HALLASAN[0]:
        poly = square(ci, cj); hallasan.append((ci, cj, poly, poly.Intersection(outline).Area() / poly.Area() * 100 if poly.Intersects(outline) else 0.0, 1))
h_ids = {f'I{c[0]:04d}J{c[1]:04d}' for c in hallasan}
xmin, xmax, ymin, ymax = outline.GetEnvelope()
# search window: the outline envelope widened by 12 km so the islets (마라도 ~11 km south of the coast) and the buffer fit
PAD = 12000
land_cells = {}
for cj in range(math.floor((ymin - PAD) / SIZE) + J0, math.ceil((ymax + PAD) / SIZE) + J0 + 1):
    for ci in range(math.floor((xmin - PAD) / SIZE) + I0, math.ceil((xmax + PAD) / SIZE) + I0 + 1):
        share = land_share(ci, cj)
        poly = square(ci, cj); touches = poly.Intersects(outline)
        if share >= 5.0 or touches:   # >= 5 % of the 50 m lattice on land, or touching the outline
            land_cells[(ci, cj)] = (share, touches)
# zone: 'land' = touches the Natural Earth outline (main island), 'islet' = DSM land not on the outline, 'sea_buffer' = within 2 km of any land cell
jeju = []; zone = {}
for (ci, cj), (share, touches) in land_cells.items():
    zone[(ci, cj)] = 'land' if touches else 'islet'
nb = int(math.ceil(COAST_BUFFER_M / SIZE))
for (ci, cj) in list(land_cells):
    for dj in range(-nb, nb + 1):
        for di in range(-nb, nb + 1):
            k = (ci + di, cj + dj)
            if k in zone or math.hypot(di * SIZE, dj * SIZE) > COAST_BUFFER_M: continue
            zone[k] = 'sea_buffer'
for (ci, cj), zn in sorted(zone.items(), key=lambda kv: (kv[0][1], kv[0][0])):
    share = land_cells[(ci, cj)][0] if (ci, cj) in land_cells else 0.0
    jeju.append((ci, cj, square(ci, cj), share, int(f'I{ci:04d}J{cj:04d}' in h_ids), zn))
assert len(hallasan) == 1849
print('jeju cells', len(jeju), {z: sum(1 for c in jeju if c[5] == z) for z in ('land', 'islet', 'sea_buffer')})

target = ROOT / 'inputs/reference/radar_grid_cells.gpkg'
drv = ogr.GetDriverByName('GPKG')
if target.exists():
    drv.DeleteDataSource(str(target))
ds = drv.CreateDataSource(str(target))
write_layer(ds, 'hallasan_grid_500m', hallasan)
write_layer(ds, 'jeju_grid_500m', jeju)
ol = ds.CreateLayer('jeju_outline', srs, ogr.wkbMultiPolygon)
for fld in outline_layer.schema:
    ol.CreateField(ogr.FieldDefn(fld.GetName(), ogr.OFTString))
f = ogr.Feature(ol.GetLayerDefn()); f.SetGeometry(outline)
for fld in outline_layer.schema:
    f.SetField(fld.GetName(), outline_feature[fld.GetName()])
ol.CreateFeature(f)
gl = ds.CreateLayer('grid_definition', None, ogr.wkbNone)
for n in ['crs_proj4', 'numbering', 'verification', 'source_api', 'verified_on']:
    gl.CreateField(ogr.FieldDefn(n, ogr.OFTString))
f = ogr.Feature(gl.GetLayerDefn())
f.SetField('crs_proj4', PROJ4); f.SetField('numbering', GRID_DEF['grid']['order'] + f'; i0={I0}, j0={J0}, cell {SIZE} m')
f.SetField('verification', json.dumps(GRID_DEF['official'])); f.SetField('source_api', GRID_DEF['source_api']); f.SetField('verified_on', GRID_DEF['verified_on'])
gl.CreateFeature(f)
ds = None
summary = {'file': 'inputs/reference/radar_grid_cells.gpkg', 'crs_proj4': PROJ4, 'hallasan_cells': len(hallasan), 'jeju_cells': len(jeju),
           'jeju_i_range': [min(c[0] for c in jeju), max(c[0] for c in jeju)], 'jeju_j_range': [min(c[1] for c in jeju), max(c[1] for c in jeju)],
           'jeju_cells_half_or_more_land': sum(1 for c in jeju if c[3] >= 50), 'hallasan_cells_inside_jeju_selection': sum(c[4] for c in jeju),
           'outline_area_km2': round(outline.Area() / 1e6, 2)}
print(json.dumps(summary, ensure_ascii=False, indent=2))
