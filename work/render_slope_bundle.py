"""QGIS project, satellite map PNG, metadata and ZIP bundle for the selected region (SLOPE_REGION, default hallasan).

Layouts: 'square' reproduces the original Hallasan page; 'wide' is the island-wide Jeju page.
"""
from pathlib import Path
import os, sys, json, csv, math, zipfile, hashlib, shutil
import warnings
warnings.filterwarnings('ignore',category=DeprecationWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT, load
cfg=load(); PREFIX=cfg['file_prefix']; SCRATCH=cfg['scratch_prefix']; MAP=cfg['map']; META=cfg['metadata']; SAT=cfg['satellite']
WORK=ROOT/'work'; OUT=ROOT/cfg['output_dir']; SHAPES=OUT/'shapefiles'
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QGIS_CUSTOM_CONFIG_PATH']=str(WORK/'qgis_slope_profile')
from osgeo import gdal, ogr, osr
from qgis.core import *
from qgis.PyQt.QtGui import QColor, QFont, QFontDatabase
from qgis.PyQt.QtCore import Qt
gdal.UseExceptions(); ogr.UseExceptions()
# Reopen flushed source rasters and validate the saved pixel values before using them in QGIS.
raster_checks={}
for source_name,out_name,unit in [(SCRATCH+'dem_utm_buffer.tif','dem_30m.tif','m'),(SCRATCH+'slope_full.tif','slope_degrees_30m.tif','degree'),(SCRATCH+'aspect_full.tif','aspect_degrees_30m.tif','degree')]:
    d=gdal.Warp(str(OUT/out_name),str(WORK/source_name),cutlineDSName=str(SHAPES/'study_boundary.shp'),cropToCutline=True,dstNodata=-9999,xRes=30,yRes=30,targetAlignedPixels=True,creationOptions=['COMPRESS=DEFLATE','TILED=YES','PREDICTOR=3'])
    d.GetRasterBand(1).SetUnitType(unit); d.FlushCache(); d=None
    d=gdal.Open(str(OUT/out_name)); arr=d.ReadAsArray(); good=arr[arr!=-9999]
    assert good.size>100000,(out_name,'empty raster')
    stats=d.GetRasterBand(1).ComputeStatistics(False)
    raster_checks[out_name]={'valid_pixels':int(good.size),'min':float(good.min()),'max':float(good.max()),'statistics':stats}
    d=None
print('SAVED_RASTERS_VERIFIED',json.dumps(raster_checks),flush=True)
app=QgsApplication([],False); app.initQgis()
font_ids=[QFontDatabase.addApplicationFont(p) for p in ['C:/Windows/Fonts/malgun.ttf','C:/Windows/Fonts/malgunbd.ttf','C:/Windows/Fonts/arial.ttf']]
assert font_ids[0]>=0,'Korean font could not be loaded'
FONT=QFontDatabase.applicationFontFamilies(font_ids[0])[0]
app.setFont(QFont(FONT,10))
print('FONT_LOADED',FONT,font_ids,flush=True)
project=QgsProject.instance()
project.setCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
project.setTitle(MAP['project_title'])
project.setFilePathStorage(Qgis.FilePathType.Relative)

# Save a local, georeferenced satellite background, requiring no network when the bundle is opened.
extent=json.loads((WORK/'public_sources'/SAT['extent']).read_text())
xmin,ymin,xmax,ymax=extent['bounds']
gdal.Translate(str(OUT/'satellite_background.tif'),str(WORK/'public_sources'/SAT['jpg']),outputSRS='EPSG:3857',outputBounds=[xmin,ymax,xmax,ymin],creationOptions=['COMPRESS=JPEG','TILED=YES','JPEG_QUALITY=90'])

# Keep only short, relevant reference fields in Shapefiles; full caveats live in metadata.json.
SOURCE=str(ROOT/cfg['reference_gpkg'])
source=ogr.Open(SOURCE,0)
for table,name,fields in [('trails','reference_trails',['course','number','status','source']),('park','reference_park',None),('labels','reference_labels',None)]:
    layer=source.GetLayerByName(table)
    available=[f.GetName() for f in layer.schema]
    selected=fields if fields else [f for f in available if f not in ['notice','osm_ids']]
    gdal.VectorTranslate(str(SHAPES/(name+'.shp')),SOURCE,format='ESRI Shapefile',layers=[table],dstSRS='EPSG:32652',selectFields=selected,accessMode='overwrite',layerCreationOptions=['ENCODING=UTF-8'])

def vector(name,title):
    layer=QgsVectorLayer(str(SHAPES/(name+'.shp')),title,'ogr'); assert layer.isValid(),name
    project.addMapLayer(layer); return layer
background=QgsRasterLayer(str(OUT/'satellite_background.tif'),'배경: Esri 위성·항공영상')
assert background.isValid(); project.addMapLayer(background)
polys=vector('slope_classes','경사 등급: Copernicus 30m / Horn')
colours=['#ffffff','#fcffb8','#fff158','#ffd800','#ffab09','#ff7826','#f53b22','#d20000','#a40000','#7c0014']
categories=[]
for i,c in enumerate(colours):
    symbol=QgsFillSymbol.createSimple({'color':c,'outline_style':'no'})
    categories.append(QgsRendererCategory(i+1,symbol,f'{i*5}–{(i+1)*5}°' if i<9 else '45° 이상'))
polys.setRenderer(QgsCategorizedSymbolRenderer('class_id',categories)); polys.setOpacity(.38)
grid=vector('grid_slope_500m',MAP['grid_layer_title'])
grid.renderer().setSymbol(QgsFillSymbol.createSimple({'style':'no','outline_color':'255,255,255,105','outline_width':'0.07'}))
trails=vector('reference_trails','탐방로 참고 선형 · OSM 6코스')
trails.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'#00f0e1','line_width':'.48','joinstyle':'round'}))
settings=QgsPalLayerSettings(); settings.fieldName='course'; settings.placement=Qgis.LabelPlacement.Line
textformat=QgsTextFormat(); textformat.setFont(QFont(FONT,9)); textformat.setSize(9); textformat.setColor(QColor('#ffffff'))
buffer=QgsTextBufferSettings(); buffer.setEnabled(True); buffer.setSize(.6); buffer.setColor(QColor('#203034')); textformat.setBuffer(buffer); settings.setFormat(textformat)
trails.setLabeling(QgsVectorLayerSimpleLabeling(settings)); trails.setLabelsEnabled(True)
olle=None
if cfg.get('olle_shapefile') and (SHAPES/(cfg['olle_shapefile']+'.shp')).exists():
    olle=vector(cfg['olle_shapefile'],'제주올레 코스 · OSM 참고 선형')
    olle.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'#ff4fa3','line_width':'.55','joinstyle':'round','capstyle':'round'}))
    olle_settings=QgsPalLayerSettings(); olle_settings.fieldName='course'; olle_settings.placement=Qgis.LabelPlacement.Line
    olle_format=QgsTextFormat(); olle_format.setFont(QFont(FONT,8)); olle_format.setSize(8); olle_format.setColor(QColor('#ffffff'))
    olle_buffer=QgsTextBufferSettings(); olle_buffer.setEnabled(True); olle_buffer.setSize(.6); olle_buffer.setColor(QColor('#7a1d4c')); olle_format.setBuffer(olle_buffer); olle_settings.setFormat(olle_format)
    olle.setLabeling(QgsVectorLayerSimpleLabeling(olle_settings)); olle.setLabelsEnabled(True)
boundary=vector('study_boundary',MAP['boundary_layer_title'])
boundary.renderer().setSymbol(QgsFillSymbol.createSimple({'style':'no','outline_color':'#ffffff','outline_width':'.42'}))
park=vector('reference_park','국립공원 참고 경계')
park.renderer().setSymbol(QgsFillSymbol.createSimple({'style':'no','outline_color':'#9cffad','outline_width':'.35','outline_style':'dash'}))
project.layerTreeRoot().findLayer(park.id()).setItemVisibilityChecked(False)
labels=vector('reference_labels','기존 지명 참고점')
project.layerTreeRoot().findLayer(labels.id()).setItemVisibilityChecked(False)
for fn,title in [('slope_degrees_30m.tif','경사각 래스터 (도)'),('dem_30m.tif','고도 DSM (m)'),('aspect_degrees_30m.tif','경사향 래스터 (도)')]:
    layer=QgsRasterLayer(str(OUT/fn),title); assert layer.isValid(); project.addMapLayer(layer)
    project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(False)
for layer in [polys,grid,trails,boundary,park,labels]+([olle] if olle else []): layer.saveNamedStyle(str(SHAPES/(Path(layer.source().split('|')[0]).stem+'.qml')))

visible=([olle] if olle else [])+[trails,boundary,grid,polys,background]
project.layerTreeRoot().setHasCustomLayerOrder(True); project.layerTreeRoot().setCustomLayerOrder(visible+[park,labels])
view_extent=QgsRectangle(xmin,ymin,xmax,ymax)
project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(view_extent,project.crs()))
layout=QgsPrintLayout(project); layout.initializeDefaults(); layout.setName(MAP['layout_name'])
wide=MAP['layout']=='wide'
page=(300,290) if wide else (300,285)
layout.pageCollection().pages()[0].setPageSize(QgsLayoutSize(*page))
def label(text,x,y,w,h,size=10,bold=False,colour='#203034'):
    font=QFont(FONT); font.setPointSizeF(size); font.setBold(bold)
    item=QgsLayoutItemLabel(layout); item.setText(text); item.setFont(font); item.setFontColor(QColor(colour)); layout.addLayoutItem(item); item.attemptMove(QgsLayoutPoint(x,y)); item.attemptResize(QgsLayoutSize(w,h)); return item
def box(x,y,w,h,colour,stroke='none'):
    item=QgsLayoutItemShape(layout); item.setShapeType(QgsLayoutItemShape.Rectangle); item.setSymbol(QgsFillSymbol.createSimple({'color':colour,'outline_style':'no' if stroke=='none' else 'solid','outline_color':stroke,'outline_width':'.2'})); layout.addLayoutItem(item); item.attemptMove(QgsLayoutPoint(x,y)); item.attemptResize(QgsLayoutSize(w,h)); return item
box(0,0,page[0],page[1],'#f5f4ef')
label(MAP['kicker'],9,5,250,6,9,True,'#526862')
label(MAP['title'],9,12,280,12,23,True)
label('Copernicus GLO-30 DSM 별도 계산  ·  VWorld 분석값 아님',9,27,280,7,11,True,'#874022')
def mapitem(x,y,w,h,ext,layers):
    item=QgsLayoutItemMap(layout); layout.addLayoutItem(item); item.attemptMove(QgsLayoutPoint(x,y)); item.attemptResize(QgsLayoutSize(w,h)); item.setCrs(project.crs()); item.setLayers(layers); item.setKeepLayerSet(True); item.zoomToExtent(ext); item.setFrameEnabled(True); return item
def scalebar(m,x,y,unit):
    bar=QgsLayoutItemScaleBar(layout); bar.setStyle('Single Box'); bar.setLinkedMap(m); bar.applyDefaultSize(); bar.setUnits(Qgis.DistanceUnit.Kilometers); bar.setUnitsPerSegment(unit); bar.setNumberOfSegments(2); bar.setNumberOfSegmentsLeft(0); bar.setUnitLabel('km'); bar.setFont(QFont('Malgun Gothic',9)); bar.setBackgroundEnabled(True); bar.setBackgroundColor(QColor(255,255,255,210)); layout.addLayoutItem(bar); bar.attemptMove(QgsLayoutPoint(x,y)); return bar
center=QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),project.crs(),project).transform(QgsPointXY(*MAP['inset_center']))
half=MAP['inset_half_m']; inset_extent=QgsRectangle(center.x()-half,center.y()-half,center.x()+half,center.y()+half)
if not wide:
    main=mapitem(9,39,218,218,view_extent,visible)
    label('N ↑',17,43,18,9,15,True,'#ffffff')
    scalebar(main,16,245,2)
    label('경사각 (°)',234,39,60,8,12,True)
    for i in range(10):
        y=51+i*7.5
        box(235,y,9,5.5,colours[i],'#d4d2c8')
        label(f'{i*5}–{(i+1)*5}°' if i<9 else '45° 이상',247,y-.6,44,6.8,10)
    box(235,130,9,1.2,'#00d9cc'); label('OSM 탐방로 참고선',247,127.4,45,7,8.5)
    label(MAP['stats_text'],234,138,60,24,10)
    label(MAP['inset_title'],234,168,62,7,11,True)
    inset=mapitem(234,177,57,57,inset_extent,visible)
    label('수목·구조물 영향 포함 가능\n코스 전체 연결 미검증\n원격탐사 기반 참고 분석',234,237,62,20,8.5,False,'#5b655f')
    footer_y=(259,266,274)
else:
    # Island-wide page: full-width map, legend row underneath, Hallasan inset at the lower right.
    map_h=round(282*(ymax-ymin)/(xmax-xmin),1)
    main=mapitem(9,39,282,map_h,view_extent,visible)
    label('N ↑',17,43,18,9,15,True,'#ffffff')
    scalebar(main,16,39+map_h-13,10)
    top=39+map_h+4
    label('경사각 (°)',9,top,60,8,11,True)
    for i in range(10):
        x=9+i*21.5
        box(x,top+8,6,4.5,colours[i],'#d4d2c8')
        label(f'{i*5}–{(i+1)*5}°' if i<9 else '45° 이상',x+7,top+7.2,15,6.5,8)
    box(9,top+17.5,9,1.2,'#00d9cc'); label('OSM 탐방로 참고선 (한라산 6코스)',21,top+15,90,7,8.5)
    if olle:
        box(112,top+17.5,9,1.2,'#ff4fa3'); label('제주올레 코스 (OSM 참고 선형, 코스번호 라벨)',124,top+15,110,7,8.5)
    label(MAP['stats_text'],9,top+24,215,18,9.5)
    label('수목·구조물 영향 포함 가능  ·  해안 셀은 바다 픽셀 포함 가능  ·  원격탐사 기반 참고 분석',9,top+43,215,8,8.5,False,'#5b655f')
    label(MAP['inset_title'],234,top,62,7,11,True)
    inset=mapitem(234,top+8,57,57,inset_extent,visible)
    footer_y=(page[1]-31,page[1]-24,page[1]-16)
label('고도: Copernicus GLO-30 (2021 배포본)  |  배경: Esri, Vantor, Earthstar Geographics, GIS User Community',9,footer_y[0],284,6,7.8)
label(MAP['footer_note'],9,footer_y[1],284,6,7.8)
credit='produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.'
label(credit,9,footer_y[2],284,6,5.8)
project.layoutManager().addLayout(layout)
project_path=OUT/(PREFIX+'_slope.qgs'); project.setFileName(str(project_path)); assert project.write(),project.error()
exporter=QgsLayoutExporter(layout); settings=QgsLayoutExporter.ImageExportSettings(); settings.dpi=240
png=OUT/(PREFIX+'_slope_satellite.png'); result=exporter.exportToImage(str(png),settings); assert result==QgsLayoutExporter.Success,result
print('MAP_RENDERED',str(png),flush=True)

# Provide complete provenance and field meanings alongside the requested GIS data.
checks=json.loads((OUT/'validation.json').read_text())
grid_count=checks['grid_count']
coverage_limit=META['coverage_note']
metadata={
 'title':META['title'], 'created':META['created'],
 'not_vworld_output':True,'user_approved_alternative':'Public DEM derived analysis',
 'elevation_source':{'dataset':'Copernicus GLO-30 DSM','release':'2021 AWS distribution','nominal_resolution':'1 arc second (~30m)','tile':'N33 E126','source_url':'https://registry.opendata.aws/copernicus-dem/','license_url':'https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf','credit':credit,'required_notice_ko':'법률 또는 위임에 따라 Copernicus 프로그램을 담당하는 기관은 Copernicus WorldDEM-30의 어떠한 사용에 대해서도 책임을 지지 않습니다. 재배포 시 원자료 출처·수정 사실·이 고지와 원 라이선스의 의무를 이어서 알려야 합니다.'},
 'processing':{'crs':'EPSG:32652 WGS 84 / UTM zone 52N','raster_resolution_m':30,'reprojection':'bilinear','slope':'GDAL Horn, degrees, horizontal and vertical units metres, scale=1','zonal_statistics':'Exact raster-pixel intersection area weighted for each transformed existing LCC grid polygon','percent_slope':'100 * tan(slope_degrees); mean_pct is area-weighted mean of pixel percent slopes, not tan(mean_deg)','p90':'Area-weighted slope percentile','class_intervals':'[0,5), [5,10), ..., [40,45), [45,90] degrees','raster_cutline':'Pixel-centre raster mask; polygons and CSV use exact vector intersection areas','software':{'QGIS':Qgis.QGIS_VERSION,'GDAL':gdal.VersionInfo('--version')}},
 'arcgis_usage':{'used':True,'url':'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer','purpose':'Satellite/aerial background only; no slope computation or slope values from ArcGIS','reason':'Provides a georeferenced image for the study bounds, consistent with the Esri background in the existing Hallasan map','credentials_used':False,'raster_embedded_locally':True,'credit':json.loads((WORK/'public_sources/esri_service.json').read_text())['copyrightText'],'image_dates':'Mixed mosaic; acquisition dates not verified. Display only.'},
 'vworld_findings':{'page':'https://map.vworld.kr/map/dtkmap.do?mode=MAPD101','settings_page':'https://map.vworld.kr/dtkmap/dtk_t3dtpgrph_s002.do','checked_date':'2026-10-13','preset_max_area_m2':100000,'direct_input_max_area_m2':200000,'analysis':'Public page samples terrain heights in the client; screenshot distributions do not identify georeferenced slope polygons','actual_vworld_results_collected':False},
 'grid':{'count':grid_count,'source':META['grid_source'],'ids_preserved':True,'original_crs':'Assumed spherical LCC, standard parallels 30/60, radius 6371008.77m','original_plane_area_km2':META['original_plane_area_km2'],'utm_plane_area_km2':checks['area_utm_m2']/1e6,'area_difference':'Projection-scale difference. Same geographic footprint; original assumed LCC metres differ from UTM ground-scale area.','radar_alignment_verified':False},
 'limitations':['DSM includes vegetation and structures; not a bare-earth survey DTM.','30m sampling smooths small cliffs and trail-scale features; resampling does not increase source detail.','These values are not equivalent to VWorld terrain or its browser analysis method.',coverage_limit,'Full geographic raster coverage means no missing computational samples, not verified terrain accuracy.','OSM routes represent 6 reference courses; Seokgulam geometry absent; full official course coverage unverified.','No rainfall data, weather API, authentication key, or hiking safety classification used.'],
 'files':{PREFIX+'_grid_slope.csv':f'{grid_count} grid rows with UTF-8 BOM',PREFIX+'_slope_classes.csv':'Overall area by slope class','shapefiles/grid_slope_500m.shp':f'{grid_count} grid polygons with statistics','shapefiles/slope_classes.shp':'Contiguous 30m slope-class polygons clipped to study boundary',PREFIX+'_slope.qgs':'Portable QGIS project using relative local paths',PREFIX+'_slope_satellite.png':'Satellite/aerial backdrop with slope classes and reference trails'},
 'downloads':json.loads((WORK/'public_sources/download_manifest.json').read_text(encoding='utf-8'))
}
(OUT/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
fields={'grid_id':'기존 LCC 격자 식별자','i_ref':'기존 추정 LCC 열 번호 (1 기반)','j_ref':'기존 추정 LCC 행 번호 (1 기반)','lon':'격자 중심 경도 WGS84','lat':'격자 중심 위도 WGS84','area_m2':'EPSG:32652 격자 폴리곤 면적 m²','valid_m2':'유효 경사 표본의 격자 내 교차면적 m²','cover_pct':'valid_m2 / area_m2 ×100; 정확도 지표 아님','n_px':'조금이라도 겹치는 유효 30m 픽셀 수','mean_deg':'교차면적 가중 평균 경사각 °','p90_deg':'교차면적 가중 90백분위 경사각 °','max_deg':'격자와 겹치는 표본의 최대 경사각 °','min_deg':'최소 경사각 °','sd_deg':'교차면적 가중 경사각 표준편차 °','mean_pct':'픽셀별 tan(경사각)×100의 교차면적 가중 평균 %','elev_mean':'면적 가중 평균 DSM 고도 m','elev_min':'최소 DSM 고도 m','elev_max':'최대 DSM 고도 m','asp_deg':'경사향의 면적 가중 원형평균; 북0 동90 남180 서270','asp_r':'경사향 평균의 집중도 0–1; 작을수록 방향 해석 제한','src_m':'처리 격자 간격 30m, 원자료 명목해상도 약30m','source':'고도 원자료','method':'계산·집계 방법'}
for i in range(10): fields[f'p{i*5:02}_{(i+1)*5:02}' if i<9 else 'p45_plus']=f'{i*5}–{(i+1)*5}°'+' 범주의 유효 교차면적 비율 %' if i<9 else '45° 이상 범주의 유효 교차면적 비율 %'
with (OUT/'field_dictionary.csv').open('w',encoding='utf-8-sig',newline='') as f:
    wr=csv.writer(f); wr.writerow(['field','meaning']); wr.writerows(fields.items())

saved=QgsProject(); assert saved.read(str(project_path)); assert all(l.isValid() for l in saved.mapLayers().values())
shp_checks={}
for shp in SHAPES.glob('*.shp'):
    d=ogr.Open(str(shp),0); layer=d.GetLayer(0); invalid=0
    for feature in layer:
        if feature.GetGeometryRef() is None or not feature.GetGeometryRef().IsValid(): invalid+=1
    shp_checks[shp.name]={'features':layer.GetFeatureCount(),'invalid_geometries':invalid,'sidecars_present':all(shp.with_suffix(ext).exists() for ext in ['.shx','.dbf','.prj','.cpg'])}
    assert invalid==0 and shp_checks[shp.name]['sidecars_present']
checks.update(qgis_project_reopened_all_layers_valid=True,shapefiles=shp_checks,rasters=raster_checks,png_created=True)
(OUT/'validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
zip_path=OUT.parent/(PREFIX+'_slope_QGIS_SHP.zip')
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for file in sorted(OUT.rglob('*')):
        if file.is_file() and not file.name.endswith('~'): z.write(file,Path(PREFIX+'_slope')/file.relative_to(OUT))
with zipfile.ZipFile(zip_path) as z: assert z.testzip() is None
print('BUNDLE_COMPLETE',json.dumps({'zip':str(zip_path),'zip_bytes':zip_path.stat().st_size,'shapefile_validation':shp_checks},ensure_ascii=False),flush=True)
