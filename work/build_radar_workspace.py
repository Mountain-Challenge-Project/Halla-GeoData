from pathlib import Path
import os, json, shutil, csv
os.environ['QT_QPA_PLATFORM']='offscreen'
from osgeo import gdal, ogr, osr
import numpy as np
from qgis.core import *
from qgis.PyQt.QtGui import QColor

ROOT=Path(__file__).resolve().parent.parent
SRC=ROOT/'outputs/hallasan_course_slope_v2'
OUT=ROOT/'outputs/hallasan_radar_layers_v1'
for p in ['dist/data','dist/state','dist/frames','qgis/static','input','tests']:
    (OUT/p).mkdir(parents=True,exist_ok=True)
app=QgsApplication([],False);app.initQgis()
gdal.UseExceptions()
def srs(code):
    x=osr.SpatialReference();x.ImportFromEPSG(code);x.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER);return x
def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
def export(name):
    ds=ogr.Open(str(SRC/'shapefiles'/f'{name}.shp'));ly=ds.GetLayer()
    source=ly.GetSpatialRef();source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr=osr.CoordinateTransformation(source,srs(4326));fs=[]
    for f in ly:
        g=f.GetGeometryRef().Clone();g.Transform(tr)
        fs.append({'type':'Feature','properties':dict(f.items()),'geometry':json.loads(g.ExportToJson())})
    fc={'type':'FeatureCollection','features':fs};write(OUT/'qgis/static'/f'{name}.geojson',fc);return fc
names=['grid_slope_500m','course_summary','steep_sections','study_boundary']
data={name:export(name) for name in names}
rows=list(csv.DictReader((SRC/'course_summary.csv').open(encoding='utf-8-sig')))
sat=gdal.Warp('',str(SRC/'data/satellite_background.tif'),format='MEM',dstSRS='EPSG:3857',width=1500,resampleAlg='bilinear')
gt=sat.GetGeoTransform();bounds=[gt[0],gt[3]+sat.RasterYSize*gt[5],gt[0]+sat.RasterXSize*gt[1],gt[3]]
gdal.Translate(str(OUT/'dist/data/background.png'),sat,format='PNG')
slope=gdal.Warp('',str(SRC/'data/slope_degrees_30m.tif'),format='MEM',dstSRS='EPSG:3857',outputBounds=bounds,width=sat.RasterXSize,height=sat.RasterYSize,resampleAlg='near',dstNodata=-9999)
a=slope.ReadAsArray();colors=['5e4fa2','3288bd','66c2a5','abdda4','e6f598','fee08b','fdae61','f46d43','d53e4f','9e0142']
rgba=np.zeros((4,a.shape[0],a.shape[1]),np.uint8)
for i,c in enumerate(colors):
    mask=(a>=i*5)&(a<(i+1)*5 if i<9 else a<=90)
    for b in range(3):rgba[b,mask]=int(c[b*2:b*2+2],16)
    rgba[3,mask]=180
mem=gdal.GetDriverByName('MEM').Create('',a.shape[1],a.shape[0],4,gdal.GDT_Byte)
for i in range(4):mem.GetRasterBand(i+1).WriteArray(rgba[i])
gdal.Translate(str(OUT/'dist/data/slope.png'),mem,format='PNG')
data.update({'bounds3857':bounds,'course_rows':rows,'slope_colors':['#'+x for x in colors],
             'grid_note':'1,849개 LCC 500m 참고격자. 기상청 원격자와 동일한 정렬이라고 확인되지 않음.',
             'credits':'배경: Esri, Vantor, Earthstar Geographics, GIS User Community. 지형: Copernicus WorldDEM-30 / DLR / Airbus / EU / ESA. 탐방로: 기존 OSM 자료.',
             'terrain_attribution':'produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.'})
write(OUT/'dist/data/static.json',data)
for name in ['satellite_background','slope_degrees_30m','dem_30m']:
    for ext in ['tif','qml']:
        shutil.copy2(SRC/'data'/f'{name}.{ext}',OUT/'qgis/static'/f'{name}.{ext}')
shutil.copy2(SRC/'metadata/course_method.json',OUT/'qgis/static/course_method.json')
shutil.copy2(SRC/'metadata/terrain_metadata.json',OUT/'qgis/static/terrain_metadata.json')
write(OUT/'dist/state/latest.json',{'schema_version':1,'status':'waiting','frame_id':None,'observed_at':None,'message':'실제 강우강도 자료 미입력 · 강수값 없음','poll_seconds':60})
write(OUT/'dist/state/history.json',{'schema_version':1,'frames':[]})

P=QgsProject.instance();P.setCrs(QgsCoordinateReferenceSystem('EPSG:32652'));P.setFilePathStorage(Qgis.FilePathType.Relative)
P.setTitle('한라산 · 지형 + 레이더 공통 레이어 (실제 레이더 입력 대기)')
live=P.layerTreeRoot().addGroup('01 레이더 동기화 · 입력 대기');static=P.layerTreeRoot().addGroup('02 기존 지형 · 선택 표시')
ls=[]
for name,label,color,width in [('steep_sections','급경사 지형 구간 · 20° 이상','#fc8b49','1.1'),('course_summary','탐방로 · 이름','#ffffff','0.7'),('grid_slope_500m','500m 참고격자 · 레이더 정렬 미검증','#b8d7dd','0.12')]:
    l=QgsVectorLayer(str(OUT/'qgis/static'/f'{name}.geojson'),label,'ogr');assert l.isValid()
    if l.geometryType()==Qgis.GeometryType.Line:
        l.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':color,'line_width':width}))
    else:l.renderer().setSymbol(QgsFillSymbol.createSimple({'style':'no','outline_color':color,'outline_width':width}))
    if name=='course_summary':
        settings=QgsPalLayerSettings();settings.fieldName='course';settings.placement=Qgis.LabelPlacement.Line
        form=QgsTextFormat();form.setColor(QColor('white'));form.setSize(10);buf=QgsTextBufferSettings();buf.setEnabled(True);buf.setColor(QColor('#172c36'));buf.setSize(1);form.setBuffer(buf);settings.setFormat(form)
        l.setLabeling(QgsVectorLayerSimpleLabeling(settings));l.setLabelsEnabled(True)
    P.addMapLayer(l,False);static.addLayer(l).setItemVisibilityChecked(name!='grid_slope_500m');ls.append(l)
for name,title,visible in [('slope_degrees_30m','지형 경사각 · 도',False),('dem_30m','Copernicus 표면고도 · m',False),('satellite_background','Esri 위성·항공영상 · 기존 로컬 사본',True)]:
    l=QgsRasterLayer(str(OUT/'qgis/static'/f'{name}.tif'),title);assert l.isValid();l.loadNamedStyle(str(OUT/'qgis/static'/f'{name}.qml'));P.addMapLayer(l,False);static.addLayer(l).setItemVisibilityChecked(visible);ls.append(l)
e=QgsCoordinateTransform(ls[1].crs(),P.crs(),P).transformBoundingBox(ls[1].extent());e.scale(1.4);P.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(e,P.crs()))
P.setCustomVariables({'radar_status':'입력 대기','radar_time_kst':'관측 없음'})
P.setFileName(str(OUT/'qgis/hallasan_live.qgs'));assert P.write()
print(json.dumps({'output':str(OUT),'counts':{n:len(data[n]['features']) for n in names},'bounds3857':bounds},ensure_ascii=False))
