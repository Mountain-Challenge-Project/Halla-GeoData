from pathlib import Path
import os,json,zipfile,hashlib,datetime,uuid
os.environ['QT_QPA_PLATFORM']='offscreen'
from qgis.core import *
from qgis.PyQt.QtGui import QFont,QColor,QFontDatabase
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'outputs/hallasan_radar_layers_v1'
app=QgsApplication([],False);app.initQgis();fid=QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf');family=QFontDatabase.applicationFontFamilies(fid)[0]
P=QgsProject.instance();assert P.read(str(OUT/'qgis/hallasan_live.qgs'))
layers=list(P.mapLayers().values());assert len(layers)==6 and all(l.isValid() for l in layers)
grid=next(l for l in layers if '500m' in l.name())
project_extent=QgsCoordinateTransform(grid.crs(),P.crs(),P).transformBoundingBox(grid.extent());project_extent.scale(1.03)
assert project_extent.xMinimum()>100000 and project_extent.yMinimum()>3000000
P.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(project_extent,P.crs()));assert P.write()
layout=QgsPrintLayout(P);layout.initializeDefaults();layout.pageCollection().pages()[0].setPageSize(QgsLayoutSize(297,245));layout.renderContext().setDpi(150)
def label(text,x,y,w,h,size=10,color='#24434b',bold=False):
    item=QgsLayoutItemLabel(layout);item.setText(text);font=QFont(family);font.setPointSizeF(size);font.setBold(bold);item.setFont(font);item.setFontColor(QColor(color));layout.addLayoutItem(item);item.attemptMove(QgsLayoutPoint(x,y));item.attemptResize(QgsLayoutSize(w,h));return item
label('한라산 · 지형 위에 겹치는 기상레이더',10,5,277,12,18,bold=True)
label('입력 대기  |  실제 레이더 강수값 없음  |  웹 · VWorld 배경 연결 · QGIS 공통 자료 구조',10,19,280,8,9,color='#9a6520')
chosen=[]
for key in ['급경사','탐방로','500m','지형 경사','Esri']:
    chosen.append(next(l for l in layers if key in l.name()))
chosen[3].setOpacity(.38)
mapitem=QgsLayoutItemMap(layout);layout.addLayoutItem(mapitem);mapitem.attemptMove(QgsLayoutPoint(10,32));mapitem.attemptResize(QgsLayoutSize(200,200));mapitem.setCrs(P.crs());mapitem.setLayers(chosen)
mapitem.zoomToExtent(project_extent)
label('표시된 기존 자료',218,34,70,8,12,bold=True)
label('전체 참고격자  1,849개\n탐방로  6개 코스\n급경사 구간  55개\nCopernicus DSM 파생 경사',218,47,73,30,10)
label('지형 경사각 (°)',218,86,70,8,11,bold=True)
colors=['#5e4fa2','#3288bd','#66c2a5','#abdda4','#e6f598','#fee08b','#fdae61','#f46d43','#d53e4f','#9e0142']
for i,c in enumerate(colors):
    box=QgsLayoutItemShape(layout);box.setShapeType(QgsLayoutItemShape.Rectangle);box.setSymbol(QgsFillSymbol.createSimple({'color':c,'outline_style':'no'}));layout.addLayoutItem(box);box.attemptMove(QgsLayoutPoint(219,97+i*7));box.attemptResize(QgsLayoutSize(10,4));label(f'{i*5}–{i*5+5} 미만' if i<9 else '45 이상',233,95+i*7,54,7,9)
label('강수 동기화',218,174,70,8,11,bold=True)
label('로컬 TIFF 입력\n→ 단위·격자 검사\n→ 면적 / 길이 가중 집계\n→ 동일 시각 레이어 공개\n→ 웹·QGIS 60초 갱신',218,187,73,37,9)
label('경사는 보행면 경사가 아닙니다. 참고격자는 기상청 레이더 원격자와 정렬이 확인되지 않았습니다.',10,233,282,6,8)
label('배경 Esri / Vantor / Earthstar / GIS User Community · 지형 Copernicus / DLR / Airbus / EU / ESA · 탐방로 기존 OSM',10,239,285,5,6)
exporter=QgsLayoutExporter(layout);settings=QgsLayoutExporter.ImageExportSettings();settings.dpi=150
assert exporter.exportToImage(str(OUT/'지도_레이어_미리보기.png'),settings)==QgsLayoutExporter.Success
P.clear()
report={'created':datetime.datetime.now().isoformat(),'actual_radar_api_called':False,'authentication_key_used':False,'default_radar_state':'waiting','unit_and_integration_tests':{'passed':6,'includes':['zero vs missing','area/length weighting','shared-edge ownership','unit and timezone validation','out-of-order frames and revision collision','whole Hallasan ingestion and QGIS synchronization']},'browser_checked':['local HTTP 200','six course rows plus missing Seokgulam','slope/grid switches','waiting state and no invented rainfall'],'not_verified':['VWorld authorized tile response','real KMA product decoding and alignment','production continuous collection','AWS deployment','browser PNG download event'],'qgis_base_layers':6,'counts':{'reference_grid':1849,'courses':6,'steep_sections':55}}
(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
zpath=ROOT/'outputs/hallasan_radar_3ways.zip'
with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in OUT.rglob('*'):
        if not p.is_file() or any(x in p.parts for x in ['__pycache__','.tmp']):continue
        if p.suffix in ['.pyc','.qgs~','.tmp'] or p.name.endswith('.aux.xml'):continue
        z.write(p,Path(OUT.name)/p.relative_to(OUT))
with zipfile.ZipFile(zpath) as z:
    assert z.testzip() is None
    relocation=ROOT/'work'/('radar-relocation-'+uuid.uuid4().hex[:8]);z.extractall(relocation)
assert P.read(str(relocation/OUT.name/'qgis/hallasan_live.qgs'))
assert len(P.mapLayers())==6 and all(l.isValid() for l in P.mapLayers().values())
print(json.dumps({'zip':str(zpath),'bytes':zpath.stat().st_size,'sha256':hashlib.sha256(zpath.read_bytes()).hexdigest(),'relocated_qgis_layers_valid':6,'preview':str(OUT/'지도_레이어_미리보기.png')},ensure_ascii=False))
