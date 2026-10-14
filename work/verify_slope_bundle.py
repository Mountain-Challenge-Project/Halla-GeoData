from pathlib import Path
import os, json, csv, zipfile, math
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'outputs/hallasan_slope'
os.environ['QGIS_CUSTOM_CONFIG_PATH']=str(ROOT/'work/qgis_slope_check')
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtGui import QImage
from osgeo import ogr
app=QgsApplication([],False); app.initQgis()
archive=ROOT/'outputs/hallasan_slope_QGIS_SHP.zip'
target=ROOT/'work/relocated_slope_check'
target.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name in z.namelist():
        dest=(target/name).resolve()
        assert dest.is_relative_to(target.resolve())
    z.extractall(target)
project=QgsProject(); assert project.read(str(target/'hallasan_slope/hallasan_slope.qgs'))
layers={l.name():l.isValid() for l in project.mapLayers().values()}
assert len(layers)==10 and all(layers.values()),layers
with (OUT/'hallasan_grid_slope.csv').open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
assert len(rows)==1849 and len({r['grid_id'] for r in rows})==1849
layer=ogr.Open(str(OUT/'shapefiles/grid_slope_500m.shp'))
features=layer.GetLayer(0)
by_id={r['grid_id']:r for r in rows}
for ft in features:
    r=by_id[ft['grid_id']]
    for key in ['mean_deg','p90_deg','max_deg','area_m2','cover_pct']:
        assert abs(float(r[key])-ft[key])<0.00001,(ft['grid_id'],key)
classes=json.loads((OUT/'validation.json').read_text())['classes']
class_keys=[f'p{i*5:02}_{(i+1)*5:02}' if i<9 else 'p45_plus' for i in range(10)]
residual=[]
for c,k in zip(classes,class_keys):
    from_csv=sum(float(r['valid_m2'])*float(r[k])/100 for r in rows)
    difference=abs(from_csv-c['area_m2']); residual.append(difference)
    assert difference<0.01,(k,difference)
png=QImage(str(OUT/'hallasan_slope_satellite.png'))
assert not png.isNull() and png.width()>2500 and png.height()>2500
report={'status':'passed','zip_crc':'passed','relocated_project_layers':layers,'csv_rows':len(rows),'csv_shp_values_match':True,'class_area_reconciliation_max_difference_m2':max(residual),'png_dimensions':[png.width(),png.height()]}
(OUT/'delivery_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(archive,'a',zipfile.ZIP_DEFLATED) as z: z.write(OUT/'delivery_validation.json','hallasan_slope/delivery_validation.json')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
