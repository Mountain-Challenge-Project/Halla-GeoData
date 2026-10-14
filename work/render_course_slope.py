from pathlib import Path
import os,json,csv,math,html,zipfile
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'outputs/hallasan_course_slope_v2'
os.environ['QGIS_CUSTOM_CONFIG_PATH']=str(ROOT/'work/qgis_course_profile')
from qgis.core import *
from qgis.PyQt.QtGui import QColor,QFont,QFontDatabase
from qgis.PyQt.QtCore import Qt
app=QgsApplication([],False);app.initQgis()
fontid=QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf');QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgunbd.ttf')
FONT=QFontDatabase.applicationFontFamilies(fontid)[0];app.setFont(QFont(FONT,10))
P=QgsProject.instance();P.setCrs(QgsCoordinateReferenceSystem('EPSG:32652'));P.setFilePathStorage(Qgis.FilePathType.Relative)
P.setTitle('한라산 코스별 지형 경사 | 스펙트럼 색상·한글 칼럼')
COLORS=['#5e4fa2','#3288bd','#66c2a5','#abdda4','#e6f598','#fee08b','#fdae61','#f46d43','#d53e4f','#9e0142']
LABELS=[f'{i*5}–{(i+1)*5}° 미만' for i in range(9)]+['45° 이상']
groups={name:P.layerTreeRoot().addGroup(name) for name in ['01 코스 분석 · 기본 표시','02 전체 지형 · 선택 표시','03 참고 자료','04 위성 배경']}
layers={}; specs=[]
def vec(key,title,group,visible=False,file=None):
 l=QgsVectorLayer(str(OUT/'shapefiles'/f'{file or key}.shp'),title,'ogr');assert l.isValid(),key
 P.addMapLayer(l,False);node=groups[group].addLayer(l);node.setItemVisibilityChecked(visible);layers[key]=l;return l
def ras(key,title,group,visible=False):
 l=QgsRasterLayer(str(OUT/'data'/f'{key}.tif'),title);assert l.isValid(),key
 P.addMapLayer(l,False);groups[group].addLayer(l).setItemVisibilityChecked(visible);layers[key]=l;return l
def categories(l,key,kind='line',width=.95):
 cats=[]
 for i,c in enumerate(COLORS):
  sym=QgsLineSymbol.createSimple({'line_color':c,'line_width':str(width),'joinstyle':'round'}) if kind=='line' else QgsFillSymbol.createSimple({'color':c,'outline_style':'no'})
  cats.append(QgsRendererCategory(i+1,sym,LABELS[i]))
 l.setRenderer(QgsCategorizedSymbolRenderer(key,cats))
def graduate(l,key,kind='line'):
 ranges=[]
 for i,c in enumerate(COLORS):
  sym=QgsLineSymbol.createSimple({'line_color':c,'line_width':'1.2'}) if kind=='line' else QgsFillSymbol.createSimple({'color':c,'outline_color':'#dddddd','outline_width':'.07'})
  ranges.append(QgsRendererRange(i*5,90 if i==9 else (i+1)*5,sym,LABELS[i]))
 l.setRenderer(QgsGraduatedSymbolRenderer(key,ranges))
def labeling(l,field,size=10,color='white',expression=False):
 s=QgsPalLayerSettings();s.fieldName=field;s.isExpression=expression;s.placement=Qgis.LabelPlacement.Line if l.geometryType()==Qgis.GeometryType.Line else Qgis.LabelPlacement.AroundPoint
 f=QgsTextFormat();f.setFont(QFont(FONT,10));f.setSize(size);f.setColor(QColor(color));b=QgsTextBufferSettings();b.setEnabled(True);b.setSize(.75);b.setColor(QColor('#243230'));f.setBuffer(b);s.setFormat(f)
 l.setLabeling(QgsVectorLayerSimpleLabeling(s));l.setLabelsEnabled(True)
g1='01 코스 분석 · 기본 표시';g2='02 전체 지형 · 선택 표시';g3='03 참고 자료';g4='04 위성 배경'
pieces=vec('trail_slope_pieces','탐방로 위치의 지형 경사 · 30m 셀별 선분',g1,True);categories(pieces,'class_id')
steep=vec('steep_sections','급경사 연속 구간 · 20° 이상 / 구간 번호',g1)
steep.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'#fc4b23','line_width':'1.65'}));labeling(steep,'seg_id',8)
course=vec('course_summary','코스별 평균 지형 경사 · 길이 가중',g1);graduate(course,'mean_deg');labeling(course,'course',10)
trails=vec('reference_trails','기존 탐방로 · 이름 / 흰색 테두리',g1,True)
trails.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'#ffffff','line_width':'1.55','joinstyle':'round'}));labeling(trails,'course',10)
polys=vec('slope_classes','경사구간 면 · 30m 지형 / class_id',g2);categories(polys,'class_id','fill');polys.setOpacity(.4)
grid=vec('grid_slope_500m','500m 격자 면 · 평균 경사 / mean_deg',g2);graduate(grid,'mean_deg','fill');grid.setOpacity(.6)
boundary=vec('study_boundary','전체 분석 범위 · 외곽선',g2)
boundary.renderer().setSymbol(QgsFillSymbol.createSimple({'style':'no','outline_color':'#ffffff','outline_width':'.4'}))
sloper=ras('slope_degrees_30m','30m 경사각 래스터 · 도',g2)
dem=ras('dem_30m','30m 고도 DSM · m',g3)
aspect=ras('aspect_degrees_30m','30m 경사향 · 북0° 동90° 남180° 서270°',g3)
park=vec('reference_park','국립공원 참고 경계 · OSM',g3)
park.renderer().setSymbol(QgsFillSymbol.createSimple({'style':'no','outline_color':'#92f5a0','outline_width':'.4','outline_style':'dash'}))
labels=vec('reference_labels','지명 참고점 · 코스/정상 등',g3)
labels.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':'circle','color':'#ffffff','size':'2','outline_color':'#172a2a'}));labeling(labels,'label',9)
bg=ras('satellite_background','Esri World Imagery · 위성/항공영상 배경',g4,True)
def rasterstyle(layer,values,colors,labels_=None,discrete=False):
 fn=QgsColorRampShader();fn.setColorRampType(QgsColorRampShader.Discrete if discrete else QgsColorRampShader.Interpolated)
 fn.setColorRampItemList([QgsColorRampShader.ColorRampItem(v,QColor(c),(labels_[i] if labels_ else str(v))) for i,(v,c) in enumerate(zip(values,colors))])
 sh=QgsRasterShader();sh.setRasterShaderFunction(fn);rr=QgsSingleBandPseudoColorRenderer(layer.dataProvider(),1,sh);layer.setRenderer(rr)
 rr.setClassificationMin(min(values));rr.setClassificationMax(max(values))
rasterstyle(sloper,[5,10,15,20,25,30,35,40,45,90],COLORS,LABELS,True)
rasterstyle(dem,[-1,400,800,1200,1600,1930],['#224b56','#467c52','#91b15a','#d8cc90','#94735e','#ffffff'])
rasterstyle(aspect,[0,90,180,270,360],['#e55982','#f4d35e','#65bd83','#527ed5','#e55982'])
visible=[pieces,trails,bg]
P.layerTreeRoot().setHasCustomLayerOrder(True)
P.layerTreeRoot().setCustomLayerOrder([steep,pieces,course,labels,trails,boundary,park,grid,polys,sloper,dem,aspect,bg])
ext=QgsRectangle(trails.extent());ext.scale(1.17)
P.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext,P.crs()))

common={'course':'코스 이름','course_id':'코스 ID','part_id':'연결 선형 번호','from_m':'해당 선형 시작점부터 거리 m (탐방로 입구 기준 아님)','to_m':'해당 선형 끝 거리 m','length_m':'수평 선형 길이 m','mean_deg':'길이 가중 평균 지형 경사 °','max_deg':'선형과 겹친 셀의 최대 지형 경사 °','p90_deg':'길이 가중 90백분위 지형 경사 °','mean_pct':'길이 가중 평균 지형 경사율 %','valid_m':'유효 경사값이 있는 길이 m','cover_pc':'유효 길이 비율 % (정확도 아님)','steep20_m':'20° 이상 지형을 지나는 길이 m','steep30_m':'30° 이상 지형을 지나는 길이 m','steep20_pc':'20° 이상 길이 비율 %','steep30_pc':'30° 이상 길이 비율 %','seg20_n':'20° 이상 연속 구간 수','parts':'연결 선형 개수','status':'원자료 상태 및 한계','seg_id':'급경사 구간 ID','len30_m':'구간 중 30° 이상 길이 m','short30':'총 길이 30m 미만이면 1','len_rank':'코스 내 급경사 구간 길이 순위 (1이 가장 김)','start_lon':'시작 경도 WGS84','start_lat':'시작 위도 WGS84','end_lon':'끝 경도 WGS84','end_lat':'끝 위도 WGS84','piece_id':'셀 교차 선분 ID','slope_deg':'해당 30m 셀의 지형 경사각 °','class_id':'경사 구간 코드 1–10','steep20':'경사 20° 이상이면 1','steep30':'경사 30° 이상이면 1','elev_m':'해당 셀의 DSM 고도 m','px_row':'경사 래스터 행 번호 (0 기반)','px_col':'경사 래스터 열 번호 (0 기반)','poly_id':'연속 경사구간 폴리곤 ID','deg_lo':'경사각 구간 하한 ° (포함)','deg_hi':'경사각 구간 상한 ° (미포함; 마지막 90 포함)','class_txt':'경사각 범위 문자','area_m2':'UTM 평면 면적 m²','source':'자료 출처','name':'이름','number':'기존 코스 번호','osm_id':'OSM 원자료 객체 ID','label':'지도 표시 이름','kind':'지명 분류'}
griddefs={r['field']:r['meaning'] for r in csv.DictReader((OUT/'metadata/grid_field_dictionary.csv').open(encoding='utf-8-sig'))}
layer_descriptions={
'trail_slope_pieces':'선 2,979개. 기존 탐방로를 30m 경사 셀 경계에서 나눈 선분. 선분별 slope_deg로 코스 통계를 재계산하거나 급경사 기준을 바꿀 수 있음.',
'steep_sections':'선 55개. 동일 코스 연결 선형에서 20° 이상 선분이 연속하는 부분을 합친 결과. seg_id로 CSV와 연결. 실제 보행면 경사·공식 위험등급 아님.',
'course_summary':'코스별 선 6개. 길이 가중 평균·최대와 급경사 길이. 석굴암은 선형이 없어 CSV에만 결측 행으로 포함.',
'reference_trails':'기존 OSM 탐방로 선 6개. 분석 입력과 지명 라벨/선 테두리 역할. 공식 전 구간·현재 개방 상태 미검증.',
'slope_classes':'면 27,501개. 같은 5° 경사 구간의 30m 셀을 이어 붙인 연속 면. 500m 통계 격자가 아니며 원래 픽셀 경계 모양을 보존함.',
'grid_slope_500m':'면 1,849개. 기상청 레이더 합성 500m 격자(WGS84 LCC, 2026-10-15 검증) 단위 통계. 평균은 픽셀 교차면적 가중.',
'study_boundary':'면 1개. 전체 참고격자의 외곽. 국립공원 경계와 다름.',
'reference_park':'면 1개. 기존 OSM 국립공원 참고 경계. 경사 계산의 자르기 범위로 사용하지 않음.',
'reference_labels':'점 9개. 기존 코스·지명 표시용. 경사 계산에 쓰는 측정점이 아님.',
'slope_degrees_30m':'래스터. 30m 셀마다 Horn 방식으로 계산한 지형 경사각(°). 코스 교차분석의 직접 입력. -9999는 NoData.',
'dem_30m':'래스터. Copernicus GLO-30 DSM을 UTM52N 30m로 재투영한 표면 고도(m). 수목·구조물을 포함할 수 있음.',
'aspect_degrees_30m':'래스터. 경사가 향하는 방향(°). 북0/동90/남180/서270. 평탄지와 경계 밖은 NoData.',
'satellite_background':'RGB 래스터. Esri World Imagery 위성·항공영상 배경. 경사 수치 계산에는 사용하지 않았음. 원 촬영일 미검증.'}
all_fields=[]
for key,l in layers.items():
 md=l.metadata();md.setTitle(l.name());md.setAbstract(layer_descriptions[key]);l.setMetadata(md)
 if isinstance(l,QgsVectorLayer):
  for idx,f in enumerate(l.fields()):
   meaning=griddefs.get(f.name(),common.get(f.name(),f.name())) if key=='grid_slope_500m' else common.get(f.name(),f.name())
   l.setFieldAlias(idx,meaning);all_fields.append(dict(layer=key,field=f.name(),type=f.typeName(),meaning=meaning))
  # Keep raw field names stable for joins while exposing Korean explanations in forms/tables.
  l.saveNamedStyle(str(OUT/'shapefiles'/f'{key}.qml'))
 else:l.saveNamedStyle(str(OUT/'data'/f'{key}.qml'))
with (OUT/'metadata/all_layer_fields.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['layer','field','type','meaning']);w.writeheader();w.writerows(all_fields)
with (OUT/'metadata/spectrum_classes.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['class_id','min_inclusive_deg','max_exclusive_deg','hex_color','label'])
 for i,c in enumerate(COLORS):w.writerow([i+1,i*5,90 if i==9 else (i+1)*5,c,LABELS[i]])
rows=list(csv.DictReader((OUT/'course_summary.csv').open(encoding='utf-8-sig')));validrows=[r for r in rows if r['length_m']]
def font(size,bold=False):
 f=QFont(FONT);f.setPointSizeF(size);f.setBold(bold);return f
def label(layout,text,x,y,w,h,size=10,bold=False,color='#203034'):
 t=QgsLayoutItemLabel(layout);t.setText(text);t.setFont(font(size,bold));t.setFontColor(QColor(color));layout.addLayoutItem(t);t.attemptMove(QgsLayoutPoint(x,y));t.attemptResize(QgsLayoutSize(w,h));return t
def box(layout,x,y,w,h,color):
 t=QgsLayoutItemShape(layout);t.setShapeType(QgsLayoutItemShape.Rectangle);t.setSymbol(QgsFillSymbol.createSimple({'color':color,'outline_style':'no'}));layout.addLayoutItem(t);t.attemptMove(QgsLayoutPoint(x,y));t.attemptResize(QgsLayoutSize(w,h));return t
def mapitem(layout,x,y,w,h,extent,ls):
 m=QgsLayoutItemMap(layout);layout.addLayoutItem(m);m.attemptMove(QgsLayoutPoint(x,y));m.attemptResize(QgsLayoutSize(w,h));m.setCrs(P.crs());m.setLayers(ls);m.setKeepLayerSet(True);m.zoomToExtent(extent);m.setFrameEnabled(True);return m
def scale(layout,m,x,y,unit=1):
 b=QgsLayoutItemScaleBar(layout);b.setStyle('Single Box');b.setLinkedMap(m);b.applyDefaultSize();b.setUnits(Qgis.DistanceUnit.Kilometers);b.setUnitsPerSegment(unit);b.setNumberOfSegments(2);b.setNumberOfSegmentsLeft(0);b.setUnitLabel('km');b.setFont(font(8));b.setBackgroundEnabled(True);b.setBackgroundColor(QColor(255,255,255,225));layout.addLayoutItem(b);b.attemptMove(QgsLayoutPoint(x,y))
def map_note(layout,m,point,text,width=23):
 e=m.extent();p=m.positionWithUnits();sz=m.sizeWithUnits()
 x=p.x()+(point.x()-e.xMinimum())/e.width()*sz.width();y=p.y()+(e.yMaximum()-point.y())/e.height()*sz.height()
 x=max(p.x()+1,min(x-width/2,p.x()+sz.width()-width-1));y=max(p.y()+1,min(y-7,p.y()+sz.height()-6))
 occupied=getattr(m,'_note_boxes',[])
 for offset in [0,-7,7,-14,14,-21,21]:
  trial=max(p.y()+1,min(y+offset,p.y()+sz.height()-6))
  if not any(x<b[0]+b[2]+1 and x+width+1>b[0] and trial<b[1]+6.5 and trial+6.5>b[1] for b in occupied):y=trial;break
 occupied.append((x,y,width));m._note_boxes=occupied
 box(layout,x,y,width,5.5,'#253833');label(layout,text,x+.7,y-.25,width-1,6,8,True,'#ffffff')
credit='고도: Copernicus GLO-30 | 선형: © OpenStreetMap contributors | 배경: Esri, Vantor, Earthstar Geographics, GIS User Community'
lic='produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.'
def export(layout,fn):
 P.layoutManager().addLayout(layout);s=QgsLayoutExporter.ImageExportSettings();s.dpi=240
 assert QgsLayoutExporter(layout).exportToImage(str(OUT/'maps'/fn),s)==QgsLayoutExporter.Success
 print('RENDERED',fn,flush=True)
layout=QgsPrintLayout(P);layout.initializeDefaults();layout.setName('코스 경사 전체 지도');layout.pageCollection().pages()[0].setPageSize(QgsLayoutSize(320,248))
box(layout,0,0,320,248,'#f5f4ef');label(layout,'HALLASAN  /  COURSE TERRAIN',10,5,290,6,9,True,'#527068')
label(layout,'한라산 코스별 지형 경사',10,13,300,12,23,True)
label(layout,'기존 탐방로 × Copernicus 30m DSM  ·  실제 보행면 기울기와 구분',10,27,300,7,11,True,'#8c482a')
m=mapitem(layout,10,40,200,181,ext,visible);label(layout,'N ↑',15,43,20,10,16,True,'white');scale(layout,m,16,209)
label(layout,'길이 가중 평균 / 최대 경사',218,39,95,8,12,True)
for feature in course.getFeatures():
 if feature['course']=='어승생악':map_note(layout,m,feature.geometry().interpolate(feature.geometry().length()/2).asPoint(),'어승생악',22)
label(layout,'코스',218,49,30,7,9,True);label(layout,'평균',250,49,29,7,9,True);label(layout,'최대',280,49,30,7,9,True)
for i,r in enumerate(validrows):
 y=58+i*13
 label(layout,r['course'],218,y,30,7,10,True)
 label(layout,f"{float(r['mean_deg']):.2f}°",250,y,29,7,10)
 label(layout,f"{float(r['max_deg']):.2f}°",280,y,30,7,10)
 label(layout,f"20° 이상  {float(r['steep20_m']):,.0f}m  ({float(r['steep20_pc']):.1f}%)",218,y+6,95,6,8,False,'#5a6e69')
label(layout,'지형 경사 스펙트럼',218,139,95,7,11,True)
for i,c in enumerate(COLORS):
 x=219+(i//5)*48;y=150+(i%5)*7
 box(layout,x,y,8,4.5,c);label(layout,LABELS[i].replace(' 미만',''),x+10,y-1,35,6,8.5)
label(layout,'급경사 기준: 20° 이상 (분석용)\n30° 이상은 CSV에 별도 집계\n석굴암: 기존 선형 없어 계산 불가',218,189,96,21,9)
label(layout,'OSM 전 구간·개방 상태 미검증\n30m DSM: 수목/구조물 영향 포함',218,212,96,14,8,False,'#5a6e69')
label(layout,credit,10,226,305,6,7.5);label(layout,'2026-10-13  |  급경사 등급은 공식 위험등급이 아닙니다. 평균은 격자 면적이 아닌 탐방로 교차 길이로 가중했습니다.',10,233,305,6,7.5)
label(layout,lic,10,240,305,6,5.5);export(layout,'course_slope_overview.png')

# Six detailed maps isolate one course at a time; labels identify the two longest steep sections per course.
detail=QgsPrintLayout(P);detail.initializeDefaults();detail.setName('6코스 급경사 상세 지도');detail.pageCollection().pages()[0].setPageSize(QgsLayoutSize(300,348))
box(detail,0,0,300,348,'#f5f4ef');label(detail,'코스별 급경사 구간 · 20° 이상',10,6,280,11,21,True)
label(detail,'주황색 선: 20° 이상 지형  |  번호: 코스별 가장 긴 2개 구간  |  전체 55개 구간은 CSV·QGIS에서 확인',10,19,280,8,9)
detail_layers=[]
for i,r in enumerate(validrows):
 x=10+(i%2)*145;y=32+(i//2)*99
 cc=course.clone();cc.setSubsetString(f'"course_id" = \'{r["course_id"]}\'');cc.setLabelsEnabled(False);cc.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({'line_color':'white','line_width':'1.25'})))
 ss=steep.clone();ss.setSubsetString(f'"course_id" = \'{r["course_id"]}\'');ss.setLabelsEnabled(False)
 detail_layers.extend([cc,ss]);P.addMapLayer(cc,False);P.addMapLayer(ss,False)
 e=QgsRectangle(cc.extent());e.scale(1.18)
 label(detail,f"{r['course']}  평균 {float(r['mean_deg']):.2f}° / 최대 {float(r['max_deg']):.2f}°",x,y,136,7,10,True)
 mm=mapitem(detail,x,y+9,135,73,e,[ss,cc,bg]);scale(detail,mm,x+3,y+69,0.25 if r['course']=='어승생악' else 1)
 for feature in ss.getFeatures():
  if feature['len_rank']<=2:map_note(detail,mm,feature.geometry().interpolate(feature.geometry().length()/2).asPoint(),feature['seg_id'])
 label(detail,f"20° 이상 {float(r['steep20_m']):,.0f}m · {r['seg20_n']}구간  |  선형 {float(r['length_m'])/1000:.2f}km",x,y+83,138,8,8.5)
label(detail,credit,10,329,280,6,6.8);label(detail,'선형 완전성 미검증. from_m/to_m은 저장된 선형 시작점 기준이며 공식 입구 누적거리가 아닙니다.',10,335,280,6,7.2)
label(detail,lic,10,342,280,5,5.2);export(detail,'course_steep_detail.png')
# Include hidden map-layout layers in a closed reference group so layouts remain portable.
hidden=P.layerTreeRoot().addGroup('05 인쇄지도 전용 · 수정 불필요')
for l in detail_layers:
 hidden.addLayer(l).setItemVisibilityChecked(False)
hidden.setExpanded(False)
P.setFileName(str(OUT/'hallasan_course_slope.qgs'));assert P.write(),P.error()
(OUT/'metadata/layer_descriptions.json').write_text(json.dumps(layer_descriptions,ensure_ascii=False,indent=2),encoding='utf-8')
print('PROJECT_SAVED',len(P.mapLayers()),flush=True)
