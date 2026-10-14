from pathlib import Path
import json
from osgeo import ogr, gdal
R=Path(__file__).resolve().parent.parent/'outputs/hallasan_slope'
for p in sorted((R/'shapefiles').glob('*.shp')):
 d=ogr.Open(str(p)); l=d.GetLayer(0)
 print(json.dumps({'file':p.name,'count':l.GetFeatureCount(),'type':ogr.GeometryTypeToName(l.GetGeomType()),'fields':[(f.GetName(),f.GetTypeName()) for f in l.schema],'sample':next(iter(l)).items()},ensure_ascii=False))
 if p.stem=='reference_trails':
  for f in l:
   g=f.GetGeometryRef(); parts=[g] if g.GetGeometryName()=='LINESTRING' else [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())]
   print(json.dumps({'course':f.items(),'length_m':g.Length(),'parts':[round(v.Length(),3) for v in parts],'points':[v.GetPointCount() for v in parts]},ensure_ascii=False))
for fn in ['slope_degrees_30m.tif','dem_30m.tif']:
 d=gdal.Open(str(R/fn)); print(fn,d.GetGeoTransform(),d.RasterXSize,d.RasterYSize)
