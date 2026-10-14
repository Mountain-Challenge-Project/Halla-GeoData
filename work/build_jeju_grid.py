"""Extend the assumed-LCC 500m reference grid from the Hallasan block to the whole of Jeju.

Keeps the Hallasan convention exactly: spherical LCC (lat1=30, lat2=60, R=6371008.77 m,
origin 126E/38N), 500 m cells, 1-based cell numbering with the reference cell centre
i0=1121 / j0=1681 at LCC (0, 0), and ids formatted I%04dJ%04d. A cell is kept when its
square touches the Natural Earth 1:10m Jeju outline stored in the existing GeoPackage.
Official radar grid alignment remains unverified, as for the Hallasan grid.
"""
from pathlib import Path
import json, math, sys
from osgeo import ogr, osr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT, load

ogr.UseExceptions(); osr.UseExceptions()
cfg = load('jeju')
hallasan = load('hallasan')
I0, J0, SIZE = 1121, 1681, 500
src = ogr.Open(str(ROOT / hallasan['grid_gpkg']), 0)
outline_layer = src.GetLayerByName('jeju_outline')
outline_feature = next(iter(outline_layer))
outline = outline_feature.GetGeometryRef().Clone()
lcc = outline_layer.GetSpatialRef().Clone()
old = src.GetLayerByName(hallasan['grid_layer'])
old_ids = {f['ref_id'] for f in old}
old.ResetReading()
old_feature = next(iter(old))
source_text = old_feature['source']
notice = ('추정 LCC / 공식 레이더 정렬 미검증. lat1=30,lat2=60,R=6371008.77m 및 1기반 기준셀 중심 i0=1121,j0=1681을 가정. '
          '한라산 격자와 같은 규칙으로 제주 전역까지 확장. 셀 선택 기준은 Natural Earth 1:10m 제주 외곽선과의 교차이며 정밀 해안선이 아님. '
          '실제 API 수신·인증키·기상값 없음.')


def square(ci, cj):
    x0 = (ci - I0) * SIZE - SIZE / 2
    y0 = (cj - J0) * SIZE - SIZE / 2
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in [(x0, y0), (x0 + SIZE, y0), (x0 + SIZE, y0 + SIZE), (x0, y0 + SIZE), (x0, y0)]:
        ring.AddPoint_2D(x, y)
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)
    return poly


xmin, xmax, ymin, ymax = outline.GetEnvelope()
i_range = range(math.floor(xmin / SIZE) + I0, math.ceil(xmax / SIZE) + I0 + 1)
j_range = range(math.floor(ymin / SIZE) + J0, math.ceil(ymax / SIZE) + J0 + 1)
cells = []
for cj in j_range:
    for ci in i_range:
        poly = square(ci, cj)
        if not poly.Intersects(outline):
            continue
        land = poly.Intersection(outline).Area() / poly.Area() * 100
        cells.append((ci, cj, poly, land))
ids = [f'I{ci:04d}J{cj:04d}' for ci, cj, _, _ in cells]
assert len(ids) == len(set(ids))
assert old_ids <= set(ids), 'every Hallasan cell must be part of the Jeju grid'

target = ROOT / cfg['grid_gpkg']
target.parent.mkdir(parents=True, exist_ok=True)
driver = ogr.GetDriverByName('GPKG')
if target.exists():
    driver.DeleteDataSource(str(target))
ds = driver.CreateDataSource(str(target))
layer = ds.CreateLayer(cfg['grid_layer'], lcc, ogr.wkbPolygon)
for name, kind in [('ref_id', ogr.OFTString), ('i_assumed', ogr.OFTInteger), ('j_assumed', ogr.OFTInteger),
                   ('center_x_m', ogr.OFTReal), ('center_y_m', ogr.OFTReal), ('size_m', ogr.OFTInteger),
                   ('area_m2', ogr.OFTReal), ('land_pct', ogr.OFTReal), ('in_hallasan', ogr.OFTInteger),
                   ('source', ogr.OFTString), ('notice', ogr.OFTString)]:
    layer.CreateField(ogr.FieldDefn(name, kind))
for (ci, cj, poly, land), ref_id in zip(cells, ids):
    f = ogr.Feature(layer.GetLayerDefn())
    f.SetGeometry(poly)
    values = {'ref_id': ref_id, 'i_assumed': ci, 'j_assumed': cj, 'center_x_m': (ci - I0) * SIZE,
              'center_y_m': (cj - J0) * SIZE, 'size_m': SIZE, 'area_m2': SIZE * SIZE, 'land_pct': land,
              'in_hallasan': int(ref_id in old_ids), 'source': source_text, 'notice': notice}
    for k, v in values.items():
        f.SetField(k, v)
    layer.CreateFeature(f)
out_layer = ds.CreateLayer('jeju_outline', lcc, ogr.wkbMultiPolygon)
for fld in outline_layer.schema:
    out_layer.CreateField(ogr.FieldDefn(fld.GetName(), ogr.OFTString))
f = ogr.Feature(out_layer.GetLayerDefn())
f.SetGeometry(outline)
for fld in outline_layer.schema:
    f.SetField(fld.GetName(), outline_feature[fld.GetName()])
out_layer.CreateFeature(f)
ds = None
summary = {'file': cfg['grid_gpkg'], 'layer': cfg['grid_layer'], 'cells': len(cells), 'hallasan_cells': len(old_ids),
           'i_range': [min(c[0] for c in cells), max(c[0] for c in cells)],
           'j_range': [min(c[1] for c in cells), max(c[1] for c in cells)],
           'cells_half_or_more_land': sum(1 for c in cells if c[3] >= 50),
           'outline_area_km2': outline.Area() / 1e6, 'lcc_plane_area_km2': len(cells) * 0.25,
           'outline_source': outline_feature['source']}
print(json.dumps(summary, ensure_ascii=False, indent=2))
