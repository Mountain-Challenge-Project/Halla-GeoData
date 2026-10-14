from pathlib import Path
import os, csv, json, math, shutil
import numpy as np
from osgeo import gdal, ogr, osr
os.environ['QT_QPA_PLATFORM']='offscreen'
from qgis.core import QgsApplication, QgsGeometry
gdal.UseExceptions(); ogr.UseExceptions()
app=QgsApplication([],False); app.initQgis()
ROOT=Path(__file__).resolve().parent.parent
BASE=ROOT/'outputs/hallasan_slope'; OUT=ROOT/'outputs/hallasan_course_slope_v2'
for p in [OUT,OUT/'data',OUT/'shapefiles',OUT/'metadata',OUT/'maps']: p.mkdir(parents=True,exist_ok=True)
for f in (BASE/'shapefiles').glob('*'):
 if f.suffix!='.qml': shutil.copy2(f,OUT/'shapefiles'/f.name)
for f in BASE.glob('*.tif'): shutil.copy2(f,OUT/'data'/f.name)
shutil.copy2(BASE/'metadata.json',OUT/'metadata/terrain_metadata.json')
shutil.copy2(BASE/'hallasan_grid_slope.csv',OUT/'data/hallasan_grid_slope.csv')
shutil.copy2(BASE/'hallasan_slope_classes.csv',OUT/'data/hallasan_slope_classes.csv')
shutil.copy2(BASE/'field_dictionary.csv',OUT/'metadata/grid_field_dictionary.csv')
ds=gdal.Open(str(BASE/'slope_degrees_30m.tif')); z=ds.ReadAsArray(); gt=ds.GetGeoTransform(); no=ds.GetRasterBand(1).GetNoDataValue()
elev=gdal.Open(str(BASE/'dem_30m.tif')).ReadAsArray()
utm=osr.SpatialReference(); utm.ImportFromEPSG(32652); utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
wgs=osr.SpatialReference(); wgs.ImportFromEPSG(4326); wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_wgs=osr.CoordinateTransformation(utm,wgs)
def lonlat(pt): return to_wgs.TransformPoint(pt[0],pt[1])[:2]
def line(points):
 g=ogr.Geometry(ogr.wkbLineString)
 for p in points:g.AddPoint_2D(*p[:2])
 return g
def write_csv(name,rows,fields=None):
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader()
  for row in rows:w.writerow({k:(round(v,8) if isinstance(v,float) else v) for k,v in row.items() if not k.startswith('_')})
def shape(name,rows,typ):
 p=OUT/'shapefiles'/f'{name}.shp'; driver=ogr.GetDriverByName('ESRI Shapefile')
 if p.exists():driver.DeleteDataSource(str(p))
 d=driver.CreateDataSource(str(p)); l=d.CreateLayer(name,utm,typ,options=['ENCODING=UTF-8'])
 fields=[k for k in rows[0] if not k.startswith('_')]
 for key in fields:
  values=[r.get(key) for r in rows if r.get(key) is not None]
  v=values[0] if values else ''
  t=ogr.OFTReal if any(isinstance(a,float) for a in values) else ogr.OFTInteger if isinstance(v,int) else ogr.OFTString
  fld=ogr.FieldDefn(key,t)
  if t==ogr.OFTString:fld.SetWidth(min(254,max(24,max(len(str(a).encode('utf-8')) for a in values)+2)))
  if t==ogr.OFTReal:fld.SetWidth(24);fld.SetPrecision(8)
  l.CreateField(fld)
 for row in rows:
  f=ogr.Feature(l.GetLayerDefn());f.SetGeometry(row['_geom'])
  for key in fields:
   if row.get(key) is not None:f.SetField(key,row[key])
  l.CreateFeature(f)
 d=None
def classify(v):return min(10,int(v//5)+1)
def weighted(rows):
 valid=[r for r in rows if r['slope_deg'] is not None]; ln=sum(r['length_m'] for r in valid)
 if not valid:return {}
 mean=sum(r['slope_deg']*r['length_m'] for r in valid)/ln
 ordered=sorted(valid,key=lambda x:x['slope_deg']); run=0
 p90=ordered[-1]['slope_deg']
 for r in ordered:
  run+=r['length_m']
  if run>=ln*.9:p90=r['slope_deg'];break
 return dict(valid_m=ln,mean_deg=mean,max_deg=max(r['slope_deg'] for r in valid),p90_deg=p90,
             mean_pct=sum(math.tan(math.radians(r['slope_deg']))*100*r['length_m'] for r in valid)/ln,
             steep20_m=sum(r['length_m'] for r in valid if r['slope_deg']>=20),steep30_m=sum(r['length_m'] for r in valid if r['slope_deg']>=30))

src=ogr.Open(str(BASE/'shapefiles/reference_trails.shp')); lyr=src.GetLayer(0)
pieces=[]; sections=[]; courses=[]; parts_meta=[]; geometry_checks=[]
for feat in lyr:
 name=feat['course']; number=str(feat['number']); course_id='C'+number.zfill(2)
 original=feat.GetGeometryRef().Clone(); qg=QgsGeometry();qg.fromWkb(bytes(original.ExportToWkb()))
 merged=qg.mergeLines(); merged=merged if not merged.isEmpty() else qg
 geom=ogr.CreateGeometryFromWkb(bytes(merged.asWkb()))
 parts=[geom] if geom.GetGeometryName()=='LINESTRING' else [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
 before=original.Length();after=geom.Length();assert abs(before-after)<1e-5
 cr=[]
 for pi,part in enumerate(parts,1):
  pts=[part.GetPoint(i)[:2] for i in range(part.GetPointCount())]
  # Original component order is retained; these are not official trailhead chainages.
  position=0.; pr=[]
  for a,b in zip(pts,pts[1:]):
   dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
   if length<1e-10:continue
   breaks=[0.,1.]
   for av,bv,origin,step in [(a[0],b[0],gt[0],gt[1]),(a[1],b[1],gt[3],gt[5])]:
    if abs(bv-av)<1e-12:continue
    lo,hi=sorted([(av-origin)/step,(bv-origin)/step])
    for k in range(math.floor(lo)+1,math.ceil(hi)):
     t=(origin+k*step-av)/(bv-av)
     if 1e-10<t<1-1e-10:breaks.append(t)
   breaks=sorted(set(round(t,13) for t in breaks))
   for ta,tb in zip(breaks,breaks[1:]):
    start=(a[0]+ta*dx,a[1]+ta*dy);end=(a[0]+tb*dx,a[1]+tb*dy)
    mid=((start[0]+end[0])/2,(start[1]+end[1])/2)
    col=math.floor((mid[0]-gt[0])/gt[1]);row=math.floor((mid[1]-gt[3])/gt[5])
    valid=0<=row<z.shape[0] and 0<=col<z.shape[1] and z[row,col]!=no and np.isfinite(z[row,col])
    slope=float(z[row,col]) if valid else None;ln=(tb-ta)*length
    begin=position+ta*length;finish=position+tb*length
    slon,slat=lonlat(start);elon,elat=lonlat(end)
    r=dict(piece_id=f'{course_id}P{pi:02}R{len(pr)+1:04}',course=name,course_id=course_id,part_id=pi,
           from_m=begin,to_m=finish,length_m=ln,slope_deg=slope,class_id=classify(slope) if valid else 0,
           steep20=int(valid and slope>=20),steep30=int(valid and slope>=30),elev_m=float(elev[row,col]) if valid else None,
           px_row=row,px_col=col,start_lon=slon,start_lat=slat,end_lon=elon,end_lat=elat,
           _geom=line([start,end]),_start=start,_end=end)
    pr.append(r)
   position+=length
  assert abs(sum(r['length_m'] for r in pr)-part.Length())<1e-6
  parts_meta.append(dict(course=name,part_id=pi,length_m=part.Length(),start=lonlat(pts[0]),end=lonlat(pts[-1])))
  groups=[];current=[]
  for r in pr:
   if r['steep20']:current.append(r)
   elif current:groups.append(current);current=[]
  if current:groups.append(current)
  for group in groups:
   st=weighted(group); coords=[group[0]['_start']]+[r['_end'] for r in group]; g=line(coords)
   sid=f'{course_id}S{1+sum(s["course_id"]==course_id for s in sections):03}'
   row=dict(seg_id=sid,course=name,course_id=course_id,part_id=pi,from_m=group[0]['from_m'],to_m=group[-1]['to_m'],
            length_m=st['valid_m'],mean_deg=st['mean_deg'],max_deg=st['max_deg'],len30_m=st['steep30_m'],
            short30=int(st['valid_m']<30),start_lon=group[0]['start_lon'],start_lat=group[0]['start_lat'],
            end_lon=group[-1]['end_lon'],end_lat=group[-1]['end_lat'],_geom=g)
   sections.append(row)
  cr.extend(pr)
 st=weighted(cr);st.update(steep20_pc=100*st['steep20_m']/st['valid_m'],steep30_pc=100*st['steep30_m']/st['valid_m'])
 rank=sorted([s for s in sections if s['course_id']==course_id],key=lambda s:s['length_m'],reverse=True)
 for n,s in enumerate(rank,1):s['len_rank']=n
 course=dict(course_id=course_id,course=name,length_m=before,parts=len(parts),cover_pc=st['valid_m']/before*100,**st,
             seg20_n=len(rank),status='기존 OSM 선형; 공식 전구간·현재 개방 미검증',_geom=original)
 courses.append(course);pieces.extend(cr)
 geometry_checks.append(dict(course=name,source_m=before,merged_m=after,pieces_m=sum(r['length_m'] for r in cr)))
 print(json.dumps({k:v for k,v in course.items() if not k.startswith('_')},ensure_ascii=False),flush=True)

summary_fields=[k for k in courses[0] if not k.startswith('_')]
missing=dict.fromkeys(summary_fields);missing.update(course_id='C07',course='석굴암',status='기존 자료에 선형 없음: 계산 불가')
write_csv('course_summary.csv',courses+[missing],summary_fields)
write_csv('steep_sections.csv',sections,[k for k in sections[0] if not k.startswith('_')])
write_csv('trail_slope_pieces.csv',pieces,[k for k in pieces[0] if not k.startswith('_')])
shape('course_summary',courses,ogr.wkbMultiLineString)
shape('steep_sections',sections,ogr.wkbLineString)
shape('trail_slope_pieces',pieces,ogr.wkbLineString)
for c in courses:
 selected=[r for r in pieces if r['course']==c['course']]
 merged=sum(s['length_m'] for s in sections if s['course']==c['course'])
 assert abs(c['steep20_m']-merged)<1e-6
 assert abs(c['valid_m']-sum(r['length_m'] for r in selected if r['slope_deg'] is not None))<1e-6

meta=dict(created='2026-10-13',method='Split existing trail line edges exactly at 30m raster cell boundaries; assign cell slope to the within-cell line segment; mean and percentiles weighted by UTM planar segment length.',
 crs='EPSG:32652',source_raster='data/slope_degrees_30m.tif',source_trails='shapefiles/reference_trails.shp',
 slope_meaning='Terrain slope (steepest surface gradient) along the mapped line, not the longitudinal gradient of a staircase/path or walking grade.',
 thresholds=dict(steep_degrees=20,additional_degrees=30,authority='Analytical cutoffs chosen for this deliverable; not official hazard classes.'),
 continuity='Only touching source parts were line-merged. No missing links or trailhead ordering inferred. from_m/to_m reset at each merged part; not official distance from trailhead.',
 maximum='Largest raster-cell terrain slope touched by a nonzero-length line segment; tiny intersections retained.',
 short_sections='short30=1 flags steep sections under one 30m pixel width. No minimum-length filtering was applied.',
 missing_course='석굴암: no source geometry; blank statistics, not zero.',
 limits=['Existing OSM line completeness/current access not verified.','30m DSM includes vegetation/structures and smooths trail-scale terrain.','Terrain slopes are not VWorld outputs.','Maximum and short steep sections are sensitive to line position and DSM resolution.','All distances are horizontal UTM planar lengths, not 3D walking distances.'],
 counts=dict(courses_with_geometry=len(courses),csv_course_rows=len(courses)+1,parts=len(parts_meta),pieces=len(pieces),steep_sections=len(sections)),parts=parts_meta)
(OUT/'metadata/course_method.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'metadata/analysis_validation.json').write_text(json.dumps(dict(status='passed',length_conservation=geometry_checks,counts=meta['counts']),ensure_ascii=False,indent=2),encoding='utf-8')
print('ANALYSIS_COMPLETE',json.dumps(meta['counts']),flush=True)
