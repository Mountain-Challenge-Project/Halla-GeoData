"""Run in QGIS Python console after opening hallasan_live.qgs. Local files only."""
from pathlib import Path
import json, datetime
from qgis.core import *
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QColor

try: hallasan_radar_timer.stop()
except NameError: pass
hallasan_root=Path(QgsProject.instance().fileName()).resolve().parent.parent
hallasan_frame_id=None
hallasan_dynamic_ids=[]
hallasan_colors=['#7ec8e3','#329bdf','#2968c8','#e5ca45','#f38b32','#d43545']
hallasan_breaks=[0.1,1,5,10,20,30]

def hallasan_rain_style(layer):
    line=layer.geometryType()==Qgis.GeometryType.Line
    root=QgsRuleBasedRenderer.Rule(None)
    def symbol(color,missing=False):
        if line:return QgsLineSymbol.createSimple({'line_color':color,'line_width':'1.1','line_style':'dash' if missing else 'solid'})
        return QgsFillSymbol.createSimple({'color':color,'outline_style':'no','style':'b_diagonal' if missing else 'solid'})
    rules=[('"rain_mean_mm_h" IS NULL','#a0adb2','결측 · 관측값 없음',True),('"rain_mean_mm_h" >= 0 AND "rain_mean_mm_h" < 0.1','#ffffff' if line else '#ffffff00','0–0.1 미만 mm/h',False)]
    for i,lo in enumerate(hallasan_breaks):
        hi=hallasan_breaks[i+1] if i+1<len(hallasan_breaks) else None
        expr=f'"rain_mean_mm_h" >= {lo}'+(f' AND "rain_mean_mm_h" < {hi}' if hi else '')
        rules.append((expr,hallasan_colors[i],f'{lo}–{hi} 미만 mm/h' if hi else f'{lo} 이상 mm/h',False))
    for expr,color,label,missing in rules:
        rule=QgsRuleBasedRenderer.Rule(symbol(color,missing));rule.setFilterExpression(expr);rule.setLabel(label);root.appendChild(rule)
    layer.setRenderer(QgsRuleBasedRenderer(root));layer.setOpacity(1 if line else .65)
    aliases={'rain_mean_mm_h':'관측된 부분의 가중 평균 강우강도 mm/h','rain_max_mm_h':'관측된 부분의 최대 강우강도 mm/h','rain_valid_pct':'유효 관측 길이/면적 비율 %','observed_at':'관측시각 UTC','frame_id':'공통 관측 자료 ID','rain_valid_m':'유효 관측 길이 m','rain_valid_m2':'유효 관측 면적 m²'}
    for k,v in aliases.items():
        ix=layer.fields().indexFromName(k)
        if ix>=0:layer.setFieldAlias(ix,v)

def hallasan_sync_once():
    global hallasan_frame_id,hallasan_dynamic_ids
    P=QgsProject.instance();group=P.layerTreeRoot().findGroup('01 레이더 동기화 · 입력 대기')
    if group is None:
        group=next((g for g in P.layerTreeRoot().children() if isinstance(g,QgsLayerTreeGroup) and g.customProperty('hallasan_live',False)),None)
    if group is None:group=P.layerTreeRoot().insertGroup(0,'01 레이더 동기화 · 입력 대기')
    group.setCustomProperty('hallasan_live',True)
    try:
        manifest=json.loads((hallasan_root/'dist/state/latest.json').read_text('utf-8'))
        if not manifest.get('frame_id'):return
        t=datetime.datetime.fromisoformat(manifest['observed_at'].replace('Z','+00:00'))
        kst=t.astimezone(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')
        old=(datetime.datetime.now(datetime.timezone.utc)-t).total_seconds()>manifest.get('stale_after_seconds',900)
        group.setName('01 레이더 · '+kst+(' · 갱신 지연' if old else ''))
        if hallasan_frame_id==manifest['frame_id']:return
        prepared=[]
        for key,name in [('steep','급경사 구간의 강우강도'),('courses','코스별 강우강도 · 길이 가중'),('grid','참고격자 강우강도 · 면적 가중')]:
            path=(hallasan_root/'dist'/manifest['assets'][key]).resolve()
            if not path.is_relative_to((hallasan_root/'dist/frames').resolve()):raise ValueError('잘못된 자료 경로')
            l=QgsVectorLayer(str(path),name,'ogr')
            if not l.isValid():raise ValueError(name+' 읽기 실패')
            if any(f['frame_id']!=manifest['frame_id'] for f in l.getFeatures()):raise ValueError('자료 시각 불일치')
            hallasan_rain_style(l);l.setCustomProperty('hallasan_dynamic',True);prepared.append(l)
        # All layers have been read and verified before replacing the previous frame.
        iface.mapCanvas().freeze(True)
        try:
            prior=[l.id() for l in P.mapLayers().values() if l.customProperty('hallasan_dynamic',False)]
            for layer in prepared:P.addMapLayer(layer,False);group.addLayer(layer)
            for layerid in prior:P.removeMapLayer(layerid)
            hallasan_dynamic_ids=[l.id() for l in prepared];hallasan_frame_id=manifest['frame_id']
            vars=P.customVariables();vars.update({'radar_status':'갱신 지연' if old else '자료 표시','radar_time_kst':kst,'radar_frame_id':hallasan_frame_id});P.setCustomVariables(vars)
        finally:iface.mapCanvas().freeze(False);iface.mapCanvas().refresh()
    except Exception as e:
        group.setName('01 레이더 · 갱신 실패 (이전 자료 유지)');print('한라산 레이더: '+str(e))

hallasan_radar_timer=QTimer();hallasan_radar_timer.timeout.connect(hallasan_sync_once);hallasan_radar_timer.start(60000)
hallasan_sync_once()
print('한라산 로컬 동기화 시작: 60초. 중지: hallasan_radar_timer.stop()')
