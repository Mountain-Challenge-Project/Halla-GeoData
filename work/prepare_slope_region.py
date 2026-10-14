from pathlib import Path
import json
from osgeo import ogr, osr

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'inputs/reference/hallasan_course_cells.gpkg'
ds = ogr.Open(str(SOURCE), 0)
layer = ds.GetLayerByName('candidate_lcc_grid_500m')
source_srs = layer.GetSpatialRef().Clone()
source_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
targets = {}
for epsg in [4326, 32652, 3857]:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    targets[epsg] = osr.CoordinateTransformation(source_srs, srs)

extents = {epsg: [float('inf'), float('inf'), -float('inf'), -float('inf')] for epsg in targets}
area_utm = 0.0
ids = []
for feature in layer:
    ids.append(feature.GetField('ref_id'))
    for epsg, transform in targets.items():
        geom = feature.GetGeometryRef().Clone()
        geom.Segmentize(50)
        geom.Transform(transform)
        xmin, xmax, ymin, ymax = geom.GetEnvelope()
        bounds = extents[epsg]
        bounds[0] = min(bounds[0], xmin)
        bounds[1] = min(bounds[1], ymin)
        bounds[2] = max(bounds[2], xmax)
        bounds[3] = max(bounds[3], ymax)
        if epsg == 32652:
            area_utm += geom.Area()

result = {
    'source_file': SOURCE.relative_to(ROOT.parent).as_posix(),
    'source_layer': layer.GetName(),
    'grid_count': len(ids),
    'unique_ids': len(set(ids)),
    'source_lcc_area_km2': len(ids) * 0.25,
    'utm52_area_km2': area_utm / 1e6,
    'bounds_by_epsg': extents,
    'notice': 'Existing assumed LCC reference grid; official radar alignment unverified. No slope observations collected in this preparation step.'
}
(ROOT / 'slope_region.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
