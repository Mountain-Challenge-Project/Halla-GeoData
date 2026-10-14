"""Local-only ingestion of verified physical rain-rate GeoTIFFs. No upstream API client."""
from pathlib import Path
import os, json, csv, math, hashlib, argparse, datetime as dt, shutil, tempfile, time, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from osgeo import gdal, osr
from qgis.core import QgsApplication, QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsFeature, QgsSpatialIndex, QgsRectangle

ROOT=Path(__file__).resolve().parent
APP=None
UTC=dt.timezone.utc
def init():
    global APP
    if APP is None: APP=QgsApplication([],False);APP.initQgis()
    gdal.UseExceptions()
def stamp():return dt.datetime.now(UTC).isoformat().replace('+00:00','Z')
def parse_time(value):
    t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('observed_at에는 UTC Z 또는 시차가 필요합니다.')
    return t.astimezone(UTC)
def replace_with_retry(source,target):
    # Windows antivirus/OneDrive and readers can briefly hold a sharing lock.
    for attempt in range(8):
        try:os.replace(source,target);return
        except PermissionError:
            if attempt==7:raise
            time.sleep(min(.1*2**attempt,1))
def atomic_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    replace_with_retry(temp,path)
def validate_metadata(m):
    required=['raster','observed_at','source_product','source_reference','quantity','unit','value_encoding','grid_verified','unit_verified','nodata_verified','verification_note','revision']
    for k in required:
        if k not in m:raise ValueError('필수 메타데이터 누락: '+k)
    if m['quantity']!='rain_rate' or m['unit']!='mm/h' or m['value_encoding']!='physical_float':
        raise ValueError('이 입력기는 물리량 강우강도(mm/h) GeoTIFF만 받습니다. dBZ·배율 정수·누적 mm는 별도 변환/입력기가 필요합니다.')
    for k in ['grid_verified','unit_verified','nodata_verified']:
        if m[k] is not True:raise ValueError(k+' 확인이 필요합니다.')
    for k in ['source_product','source_reference','verification_note']:
        if not isinstance(m[k],str) or not m[k].strip():raise ValueError(k+' 내용을 기록하세요.')
    if not isinstance(m['revision'],int) or isinstance(m['revision'],bool) or m['revision']<0:raise ValueError('revision은 0 이상의 정수입니다.')
    t=parse_time(m['observed_at'])
    if t>dt.datetime.now(UTC)+dt.timedelta(minutes=5):raise ValueError('미래 관측시각은 입력할 수 없습니다.')
    return t
def features_in_utm(fc):
    tr=QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),QgsCoordinateReferenceSystem('EPSG:32652'),QgsProject.instance())
    geometries=[];index=QgsSpatialIndex()
    for i,f in enumerate(fc['features']):
        # QgsGeometry.fromJson is not available on all supported QGIS releases.
        from osgeo import ogr
        og=ogr.CreateGeometryFromJson(json.dumps(f['geometry']));g=QgsGeometry();g.fromWkb(bytes(og.ExportToWkb()));g.transform(tr)
        q=QgsFeature(i);q.setGeometry(g);index.addFeature(q);geometries.append(g)
    return geometries,index
def aggregate(geometries,index,pixels,line=False):
    sums=[0.0]*len(geometries);valid=[0.0]*len(geometries);maxima=[None]*len(geometries);covered={}
    for pixel,value in pixels:
        for i in index.intersects(pixel.boundingBox()):
            part=geometries[i].intersection(pixel)
            if line and i in covered:part=part.difference(covered[i])
            weight=part.length() if line else part.area()
            if weight<=1e-9:continue
            if line:covered[i]=covered[i].combine(part) if i in covered else QgsGeometry(part)
            sums[i]+=value*weight;valid[i]+=weight;maxima[i]=value if maxima[i] is None else max(maxima[i],value)
    result=[]
    for i,g in enumerate(geometries):
        total=g.length() if line else g.area()
        if valid[i]>total*1.00001:raise ValueError('중복 교차로 유효 범위가 전체를 초과했습니다.')
        result.append({'rain_mean_mm_h':sums[i]/valid[i] if valid[i]>0 else None,'rain_max_mm_h':maxima[i],
            'rain_valid_pct':min(100.0,100*valid[i]/total) if total else 0.0,'rain_valid_m' if line else 'rain_valid_m2':valid[i]})
    return result
def crop_pixels(path,boundary):
    d=gdal.Open(str(path));band=d.GetRasterBand(1)
    if d.GetDriver().ShortName!='GTiff':raise ValueError('GeoTIFF 형식만 지원합니다.')
    if d.RasterCount!=1:raise ValueError('단일 밴드 강우강도 GeoTIFF가 필요합니다.')
    if not d.GetProjection():raise ValueError('좌표계가 없는 래스터입니다.')
    if band.GetScale() not in (None,1.0) or band.GetOffset() not in (None,0.0):raise ValueError('scale/offset을 먼저 물리값에 적용하세요.')
    source=QgsCoordinateReferenceSystem();source.createFromWkt(d.GetProjection())
    if not source.isValid():raise ValueError('좌표계 해석 실패')
    to_source=QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:32652'),source,QgsProject.instance())
    to_utm=QgsCoordinateTransform(source,QgsCoordinateReferenceSystem('EPSG:32652'),QgsProject.instance())
    b=QgsGeometry(boundary).densifyByDistance(250);b.transform(to_source)
    rect=b.boundingBox();gt=d.GetGeoTransform();inv=gdal.InvGeoTransform(gt)
    corners=[gdal.ApplyGeoTransform(inv,x,y) for x,y in [(rect.xMinimum(),rect.yMinimum()),(rect.xMinimum(),rect.yMaximum()),(rect.xMaximum(),rect.yMinimum()),(rect.xMaximum(),rect.yMaximum())]]
    x0=max(0,math.floor(min(x for x,y in corners))-1);y0=max(0,math.floor(min(y for x,y in corners))-1)
    x1=min(d.RasterXSize,math.ceil(max(x for x,y in corners))+1);y1=min(d.RasterYSize,math.ceil(max(y for x,y in corners))+1)
    if x1<=x0 or y1<=y0:raise ValueError('한라산 분석 범위와 겹치지 않습니다.')
    a=band.ReadAsArray(x0,y0,x1-x0,y1-y0);valid=band.GetMaskBand().ReadAsArray(x0,y0,x1-x0,y1-y0)>0;valid&=np.isfinite(a)
    if np.any(a[valid]<0):raise ValueError('결측 처리되지 않은 음수 값이 있습니다. nodata를 확인하세요.')
    pixels=[]
    for row,col in zip(*np.where(valid)):
        r,c=int(row+y0),int(col+x0)
        points=[QgsPointXY(*gdal.ApplyGeoTransform(gt,cx,ry)) for cx,ry in [(c,r),(c+1,r),(c+1,r+1),(c,r+1),(c,r)]]
        poly=QgsGeometry.fromPolygonXY([points]);poly.transform(to_utm)
        if poly.intersects(boundary):pixels.append((poly,float(a[row,col])))
    return d,pixels,[x0,y0,x1-x0,y1-y0]
def csv_features(path,fc):
    fields=list(fc['features'][0]['properties']) if fc['features'] else []
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(x['properties'] for x in fc['features'])
def publish_frame(root,record):
    state=root/'dist/state';hp=state/'history.json';history=json.loads(hp.read_text('utf-8')) if hp.exists() else {'schema_version':1,'frames':[]}
    frames=[x for x in history['frames'] if x['frame_id']!=record['frame_id']]
    for old in frames:
        if old['observed_at']==record['observed_at'] and old['revision']==record['revision']:
            raise ValueError('같은 관측시각·revision에 다른 내용입니다. 수정자료는 revision을 올리세요.')
    frames.append(record);frames.sort(key=lambda x:(parse_time(x['observed_at']),x['revision']))
    history['frames']=frames;atomic_json(hp,history)
    # The latest pointer is committed only after every immutable frame file is complete.
    atomic_json(state/'latest.json',frames[-1])
def ingest(metadata_path,root=ROOT):
    init();root=Path(root);mp=Path(metadata_path).resolve();m=json.loads(mp.read_text('utf-8-sig'));observed=validate_metadata(m)
    (root/'dist/frames').mkdir(parents=True,exist_ok=True)
    raster=(mp.parent/m['raster']).resolve()
    if not raster.is_file() or raster.suffix.lower() not in ['.tif','.tiff']:raise ValueError('로컬 GeoTIFF 파일이 필요합니다.')
    sourcehash=hashlib.sha256(raster.read_bytes()).hexdigest()
    staticpath=root/'dist/data/static.json';statichash=hashlib.sha256(staticpath.read_bytes()).hexdigest()
    digest=hashlib.sha256((sourcehash+statichash+json.dumps(m,sort_keys=True)).encode()).hexdigest()[:16]
    frameid=observed.strftime('%Y%m%dT%H%M%SZ')+'-r'+str(m['revision'])+'-'+digest
    target=root/'dist/frames'/frameid
    if target.exists():
        result=json.loads((target/'frame.json').read_text('utf-8'));publish_frame(root,result);return result
    static=json.loads(staticpath.read_text('utf-8'));boundary=features_in_utm(static['study_boundary'])[0][0]
    d,pixels,window=crop_pixels(raster,boundary)
    staging=Path(tempfile.mkdtemp(prefix='frame-',dir=str(root/'dist/frames')))
    try:
        for source,name,line in [('grid_slope_500m','grid',False),('course_summary','courses',True),('steep_sections','steep',True)]:
            fc=static[source];geoms,index=features_in_utm(fc);stats=aggregate(geoms,index,pixels,line)
            for feature,stat in zip(fc['features'],stats):
                feature['properties'].update(stat);feature['properties'].update({'observed_at':observed.isoformat().replace('+00:00','Z'),'frame_id':frameid,'rain_unit':'mm/h'})
            atomic_json(staging/(name+'.geojson'),fc);csv_features(staging/(name+'.csv'),fc)
        gdal.Translate(str(staging/'rain_native.tif'),d,srcWin=window,format='GTiff',creationOptions=['COMPRESS=DEFLATE'])
        shutil.copy2(mp,staging/'source_metadata.json')
        base='frames/'+frameid+'/'
        result={'schema_version':1,'status':'available','frame_id':frameid,'observed_at':observed.isoformat().replace('+00:00','Z'),
            'published_at':stamp(),'revision':m['revision'],'unit':'mm/h','quantity':'rain_rate','source_product':m['source_product'],
            'source_sha256':sourcehash,'static_sha256':statichash,'valid_native_pixels':len(pixels),'poll_seconds':60,'stale_after_seconds':900,
            'assets':{k:base+v for k,v in {'grid':'grid.geojson','courses':'courses.geojson','steep':'steep.geojson','raster':'rain_native.tif','course_csv':'courses.csv','grid_csv':'grid.csv','steep_csv':'steep.csv'}.items()}}
        atomic_json(staging/'frame.json',result)
        # Check conflicting revisions before making the directory visible.
        history=json.loads((root/'dist/state/history.json').read_text('utf-8'))
        if any(x['observed_at']==result['observed_at'] and x['revision']==result['revision'] and x['frame_id']!=frameid for x in history['frames']):
            raise ValueError('같은 시각·revision의 수정 충돌: revision을 올리세요.')
        if not staging.resolve().is_relative_to((root/'dist/frames').resolve()) or not target.resolve().is_relative_to((root/'dist/frames').resolve()):raise ValueError('자료 저장 경로 오류')
        d.Close();d=None
        replace_with_retry(staging,target);publish_frame(root,result);return result
    except Exception:
        if d is not None:d.Close()
        if staging.exists():shutil.rmtree(staging)
        raise
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control','no-store' if '/state/' in self.path else 'no-cache')
        self.send_header('X-Content-Type-Options','nosniff');super().end_headers()
    def log_message(self,*args):pass
def serve(root=ROOT,port=8765,duration=0):
    root=Path(root);init()
    server=ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,directory=str(root/'dist')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    print('Local: http://127.0.0.1:'+str(port)+'\nNo upstream API calls. Watching input/*.json',flush=True)
    seen={};started=time.monotonic()
    try:
        while not duration or time.monotonic()-started<duration:
            for p in sorted((root/'input').glob('*.json')):
                if p.name.endswith('.example.json'):continue
                try:
                    data=p.read_bytes();m=json.loads(data.decode('utf-8-sig'));r=(p.parent/m.get('raster','')).resolve()
                    signature=(hashlib.sha256(data).hexdigest(),r.stat().st_mtime_ns if r.is_file() else 0,r.stat().st_size if r.is_file() else 0)
                    if seen.get(str(p))==signature:continue
                    result=ingest(p,root);seen[str(p)]=signature;print('Published '+result['frame_id'],flush=True)
                    atomic_json(root/'dist/state/collector.json',{'status':'ok','checked_at':stamp(),'message':'로컬 파일 처리 완료'})
                except Exception as e:
                    print('Input rejected: '+p.name+' / '+str(e),flush=True)
                    atomic_json(root/'dist/state/collector.json',{'status':'error','checked_at':stamp(),'message':p.name+' / '+str(e)})
            time.sleep(5)
    except KeyboardInterrupt:pass
    finally:server.shutdown();server.server_close()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['serve','ingest']);parser.add_argument('metadata',nargs='?');parser.add_argument('--port',type=int,default=8765);parser.add_argument('--duration',type=int,default=0);args=parser.parse_args()
    if args.command=='serve':serve(port=args.port,duration=args.duration)
    elif not args.metadata:parser.error('metadata JSON 경로가 필요합니다.')
    else:print(json.dumps(ingest(args.metadata),ensure_ascii=False))
