"""Build the 500 m reference grids in the OFFICIAL KMA radar-composite grid definition.

Verified 2026-10-15 against nph-rdr_latlon_api (work/public_sources/kma_radar_grid.json): Lambert
conformal conic, standard parallels 30/60, origin 126E/38N, WGS84 ellipsoid; cell (i, j) centre at
((i-1121)*500, (j-1681)*500) m; 1-based numbering of the 2305 x 2881 HB composite (max error 0.78 m).
Cell ids keep the I%04dJ%04d form so they match radar cell numbers exactly.

Writes inputs/reference/radar_grid_cells.gpkg with
  hallasan_grid_500m   the 43 x 43 block i 1202-1244, j 651-693 (1,849 cells; same ids as before)
  jeju_grid_500m       every cell whose square touches the Natural Earth 1:10m Jeju outline
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
          ('size_m', ogr.OFTInteger), ('area_m2', ogr.OFTReal), ('land_pct', ogr.OFTReal), ('in_hallasan', ogr.OFTInteger), ('source', ogr.OFTString), ('notice', ogr.OFTString)]


def write_layer(ds, name, cells):
    layer = ds.CreateLayer(name, srs, ogr.wkbPolygon)
    for n, k in FIELDS:
        layer.CreateField(ogr.FieldDefn(n, k))
    for ci, cj, poly, land, in_h in cells:
        f = ogr.Feature(layer.GetLayerDefn()); f.SetGeometry(poly)
        for k, v in {'ref_id': f'I{ci:04d}J{cj:04d}', 'i_cell': ci, 'j_cell': cj, 'center_x_m': (ci - I0) * SIZE, 'center_y_m': (cj - J0) * SIZE, 'size_m': SIZE,
                     'area_m2': SIZE * SIZE, 'land_pct': land, 'in_hallasan': in_h, 'source': SOURCE, 'notice': NOTICE}.items():
            f.SetField(k, v)
        layer.CreateFeature(f)
    return layer


hallasan = []
for cj in HALLASAN[1]:
    for ci in HALLASAN[0]:
        poly = square(ci, cj); hallasan.append((ci, cj, poly, poly.Intersection(outline).Area() / poly.Area() * 100 if poly.Intersects(outline) else 0.0, 1))
h_ids = {f'I{c[0]:04d}J{c[1]:04d}' for c in hallasan}
xmin, xmax, ymin, ymax = outline.GetEnvelope()
jeju = []
for cj in range(math.floor(ymin / SIZE) + J0, math.ceil(ymax / SIZE) + J0 + 1):
    for ci in range(math.floor(xmin / SIZE) + I0, math.ceil(xmax / SIZE) + I0 + 1):
        poly = square(ci, cj)
        if poly.Intersects(outline):
            jeju.append((ci, cj, poly, poly.Intersection(outline).Area() / poly.Area() * 100, int(f'I{ci:04d}J{cj:04d}' in h_ids)))
assert len(hallasan) == 1849

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
