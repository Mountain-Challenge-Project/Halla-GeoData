from pathlib import Path
import os,json,csv,zipfile,re
from osgeo import ogr,gdal
os.environ['QT_QPA_PLATFORM']='offscreen'
from qgis.core import QgsApplication,QgsProject,QgsVectorLayer
gdal.UseExceptions();ogr.UseExceptions();app=QgsApplication([],False);app.initQgis()
R=Path(__file__).resolve().parent.parent;O=R/'outputs/hallasan_course_slope_v2'
summary=list(csv.DictReader((O/'course_summary.csv').open(encoding='utf-8-sig')))
pieces=list(csv.DictReader((O/'trail_slope_pieces.csv').open(encoding='utf-8-sig')))
steep=list(csv.DictReader((O/'steep_sections.csv').open(encoding='utf-8-sig')))
assert len(summary)==7 and len(pieces)==2979 and len(steep)==55
assert not summary[-1]['mean_deg'] and summary[-1]['course']=='석굴암'
checks={}
for name,rows,key in [('course_summary',summary[:-1],'course_id'),('steep_sections',steep,'seg_id'),('trail_slope_pieces',pieces,'piece_id')]:
 d=ogr.Open(str(O/'shapefiles'/f'{name}.shp'));l=d.GetLayer(0);assert l.GetFeatureCount()==len(rows)
 indexed={r[key]:r for r in rows};assert len(indexed)==len(rows);delta=0;invalid=0
 for f in l:
  r=indexed[f[key]];g=f.GetGeometryRef();assert g is not None
  if not g.IsValid():invalid+=1
  assert abs(g.Length()-float(r['length_m']))<1e-6
  for fld in l.schema:
   k=fld.GetName();v=f[k]
   if isinstance(v,(int,float)):
    delta=max(delta,abs(float(r[k])-v));assert abs(float(r[k])-v)<1e-7,(name,k,r[k],v)
 assert invalid==0
 checks[name]={'rows':len(rows),'invalid_geometry':invalid,'max_csv_shp_difference':delta}
ds=gdal.Open(str(O/'data/slope_degrees_30m.tif'));a=ds.ReadAsArray();gt=ds.GetGeoTransform()
source=ogr.Open(str(O/'shapefiles/reference_trails.shp'));independent=[]
def cellpoly(row,col):
 x=gt[0]+col*30;y=gt[3]-row*30;r=ogr.Geometry(ogr.wkbLinearRing)
 for pt in [(x,y),(x+30,y),(x+30,y-30),(x,y-30),(x,y)]:r.AddPoint_2D(*pt)
 p=ogr.Geometry(ogr.wkbPolygon);p.AddGeometry(r);return p
for f in source.GetLayer(0):
 name=f['course'];g=f.GetGeometryRef();cells={(int(p['px_row']),int(p['px_col'])) for p in pieces if p['course']==name};vals=[]
 for row,col in cells:
  inter=g.Intersection(cellpoly(row,col));length=inter.Length()
  if length>1e-9:vals.append((float(a[row,col]),length))
 length=sum(v[1] for v in vals);mean=sum(v*l for v,l in vals)/length;mx=max(v for v,l in vals);s20=sum(l for v,l in vals if v>=20)
 r=next(r for r in summary if r['course']==name)
 assert abs(length-float(r['length_m']))<1e-5,(name,length,r['length_m'])
 assert abs(mean-float(r['mean_deg']))<1e-6
 assert abs(mx-float(r['max_deg']))<1e-6
 assert abs(s20-float(r['steep20_m']))<1e-5
 independent.append({'course':name,'length_delta_m':length-float(r['length_m']),'mean_delta_deg':mean-float(r['mean_deg']),'steep_length_delta_m':s20-float(r['steep20_m'])})
project=QgsProject();assert project.read(str(O/'hallasan_course_slope.qgs'))
assert len(project.mapLayers())==25 and all(l.isValid() for l in project.mapLayers().values())
styles={}
for name in ['trail_slope_pieces','slope_classes','grid_slope_500m','course_summary']:
 l=QgsVectorLayer(str(O/'shapefiles'/f'{name}.shp'),name,'ogr');assert l.isValid()
 typ=l.renderer().type();styles[name]=typ
 assert typ==('categorizedSymbol' if name in ['trail_slope_pieces','slope_classes'] else 'graduatedSymbol'),(name,typ)
 assert all(l.attributeAlias(i) for i in range(len(l.fields())))
pngs={}
for p in (O/'maps').glob('*.png'):
 d=gdal.Open(str(p));assert d.RasterXSize>2000 and d.RasterYSize>2000
 pngs[p.name]=[d.RasterXSize,d.RasterYSize]
checks.update(status='passed',independent_geometry_intersection=independent,project_layers=25,standalone_qml_styles=styles,png_dimensions=pngs)
validation=O/'metadata/validation.json';validation.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
guide=(O/'START_HERE.html').read_text(encoding='utf-8')
for href in re.findall(r'(?:href|src)="([^"]+)"',guide):
 if not href.startswith(('http:','https:','#')):assert (O/href).exists(),href
zip_path=O.parent/'hallasan_course_slope_QGIS_v2.zip'
def pack():
 with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(O.rglob('*')):
   if p.is_file() and not p.name.endswith('~'):z.write(p,Path(O.name)/p.relative_to(O))
pack();destination=R/'work/course_bundle_relocation';destination.mkdir(exist_ok=True)
with zipfile.ZipFile(zip_path) as z:
 assert z.testzip() is None
 for member in z.infolist():assert (destination/member.filename).resolve().is_relative_to(destination.resolve())
 z.extractall(destination)
relocated=QgsProject();assert relocated.read(str(destination/O.name/'hallasan_course_slope.qgs'))
assert all(l.isValid() for l in relocated.mapLayers().values())
checks.update(relocated_all_25_layers_valid=True,zip_crc='passed',all_guide_links_exist=True)
validation.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8');pack()
print(json.dumps({'status':'passed','counts':{'courses':6,'missing_courses':1,'pieces':2979,'steep_sections':55},'project_layers':25,'zip_bytes':zip_path.stat().st_size,'independent_intersection':independent},ensure_ascii=False),flush=True)
