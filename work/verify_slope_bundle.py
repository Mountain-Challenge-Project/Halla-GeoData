"""Relocation, CSV/SHP and class-area checks for the selected region's slope bundle (SLOPE_REGION, default hallasan)."""
from pathlib import Path
import os, json, csv, sys, zipfile, math
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT, load
cfg=load(); PREFIX=cfg['file_prefix']
OUT=ROOT/cfg['output_dir']
os.environ['QGIS_CUSTOM_CONFIG_PATH']=str(ROOT/'work/qgis_slope_check')
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtGui import QImage
from osgeo import ogr
app=QgsApplication([],False); app.initQgis()
archive=OUT.parent/(PREFIX+'_slope_QGIS_SHP.zip')
target=ROOT/'work/relocated_slope_check'/cfg['name']
target.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name in z.namelist():
        dest=(target/name).resolve()
        assert dest.is_relative_to(target.resolve())
    z.extractall(target)
project=QgsProject(); assert project.read(str(target/(PREFIX+'_slope')/(PREFIX+'_slope.qgs')))
layers={l.name():l.isValid() for l in project.mapLayers().values()}
assert len(layers)==cfg.get('expected_layers',10) and all(layers.values()),layers
expected=cfg['expected_grid_count']
with (OUT/(PREFIX+'_grid_slope.csv')).open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
assert len(rows)==expected and len({r['grid_id'] for r in rows})==expected
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
    if cfg['boundary']=='rectangle': assert difference<0.01,(k,difference)
    else: assert difference<0.02*c['area_m2']+1e6,(k,difference)  # pixel-centre class mask vs exact cell intersections
png=QImage(str(OUT/(PREFIX+'_slope_satellite.png')))
assert not png.isNull() and png.width()>2500 and png.height()>2500
report={'status':'passed','zip_crc':'passed','relocated_project_layers':layers,'csv_rows':len(rows),'csv_shp_values_match':True,'class_area_reconciliation_max_difference_m2':max(residual),'png_dimensions':[png.width(),png.height()]}
(OUT/'delivery_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(archive,'a',zipfile.ZIP_DEFLATED) as z: z.write(OUT/'delivery_validation.json',PREFIX+'_slope/delivery_validation.json')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
