from pathlib import Path
import sys, tempfile, shutil, json, unittest, datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import processor as p
from qgis.core import QgsGeometry,QgsPointXY,QgsFeature,QgsSpatialIndex,QgsProject
from osgeo import gdal,osr
import numpy as np
TEST_TMP=p.ROOT/'tests/.tmp'
TEST_TMP.mkdir(exist_ok=True)
tempfile.tempdir=str(TEST_TMP)

def rectangle(x0,y0,x1,y1):return QgsGeometry.fromPolygonXY([[QgsPointXY(x0,y0),QgsPointXY(x1,y0),QgsPointXY(x1,y1),QgsPointXY(x0,y1),QgsPointXY(x0,y0)]])
def index(geoms):
    idx=QgsSpatialIndex()
    for i,g in enumerate(geoms):f=QgsFeature(i);f.setGeometry(g);idx.addFeature(f)
    return idx
class CalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):p.init()
    def test_zero_is_valid_and_length_weighted(self):
        g=QgsGeometry.fromPolylineXY([QgsPointXY(0,5),QgsPointXY(20,5)])
        v=p.aggregate([g],index([g]),[(rectangle(0,0,10,10),0),(rectangle(10,0,20,10),12)],True)[0]
        self.assertAlmostEqual(v['rain_mean_mm_h'],6);self.assertEqual(v['rain_max_mm_h'],12);self.assertAlmostEqual(v['rain_valid_pct'],100)
    def test_missing_is_excluded_not_zero(self):
        g=rectangle(0,0,20,10);v=p.aggregate([g],index([g]),[(rectangle(10,0,20,10),12)])[0]
        self.assertEqual(v['rain_mean_mm_h'],12);self.assertEqual(v['rain_valid_pct'],50)
        empty=p.aggregate([g],index([g]),[])[0];self.assertIsNone(empty['rain_mean_mm_h']);self.assertEqual(empty['rain_valid_pct'],0)
    def test_shared_edge_not_double_counted(self):
        g=QgsGeometry.fromPolylineXY([QgsPointXY(10,0),QgsPointXY(10,10)])
        v=p.aggregate([g],index([g]),[(rectangle(0,0,10,10),0),(rectangle(10,0,20,10),12)],True)[0]
        self.assertEqual(v['rain_valid_pct'],100);self.assertEqual(v['rain_mean_mm_h'],0)
    def test_units_and_missing_timezone_rejected(self):
        m=json.loads((p.ROOT/'input/radar.example.json').read_text('utf-8'));m.update(grid_verified=True,unit_verified=True,nodata_verified=True)
        m['unit']='dBZ'
        with self.assertRaises(ValueError):p.validate_metadata(m)
        m['unit']='mm/h';m['observed_at']='2020-01-01T00:00:00'
        with self.assertRaises(ValueError):p.validate_metadata(m)
    def test_latest_never_regresses(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for day in [2,1]:p.publish_frame(root,{'frame_id':str(day),'observed_at':f'2020-01-0{day}T00:00:00Z','revision':0})
            self.assertEqual(json.loads((root/'dist/state/latest.json').read_text())['frame_id'],'2')
            with self.assertRaises(ValueError):p.publish_frame(root,{'frame_id':'conflict','observed_at':'2020-01-02T00:00:00Z','revision':0})

class EndToEndTests(unittest.TestCase):
    def test_ingest_qgis_and_duplicate(self):
        p.init()
        # OGR may retain a provider pool handle until QGIS shuts down on Windows.
        with tempfile.TemporaryDirectory(prefix='hallasan-test-',ignore_cleanup_errors=True) as d:
            root=Path(d)
            for folder in ['dist/data','dist/state','dist/frames','input','qgis']:(root/folder).mkdir(parents=True,exist_ok=True)
            shutil.copy2(p.ROOT/'dist/data/static.json',root/'dist/data/static.json')
            p.atomic_json(root/'dist/state/history.json',{'schema_version':1,'frames':[]})
            static=json.loads((root/'dist/data/static.json').read_text('utf-8'));geom=p.features_in_utm(static['study_boundary'])[0][0];r=geom.boundingBox()
            nx=int((r.width()+2000)/500)+1;ny=int((r.height()+2000)/500)+1
            a=np.full((ny,nx),12,dtype=np.float32);a[:,:nx//3]=0;a[:,nx*2//3:]=-9999
            raster=root/'input/TEST_ONLY.tif';ds=gdal.GetDriverByName('GTiff').Create(str(raster),nx,ny,1,gdal.GDT_Float32);s=osr.SpatialReference();s.ImportFromEPSG(32652);ds.SetProjection(s.ExportToWkt());ds.SetGeoTransform((r.xMinimum()-1000,500,0,r.yMaximum()+1000,0,-500));ds.GetRasterBand(1).SetNoDataValue(-9999);ds.GetRasterBand(1).WriteArray(a);ds=None
            m={'raster':'TEST_ONLY.tif','observed_at':'2020-01-01T00:00:00Z','source_product':'SYNTHETIC_UNIT_TEST_NOT_OBSERVATION','source_reference':'unit test','quantity':'rain_rate','unit':'mm/h','value_encoding':'physical_float','grid_verified':True,'unit_verified':True,'nodata_verified':True,'verification_note':'controlled test fixture','revision':0}
            mp=root/'input/TEST_ONLY.json';p.atomic_json(mp,m);record=p.ingest(mp,root);again=p.ingest(mp,root)
            self.assertEqual(record['frame_id'],again['frame_id'])
            self.assertEqual(len(json.loads((root/'dist/state/history.json').read_text())['frames']),1)
            grid=json.loads((root/'dist'/record['assets']['grid']).read_text('utf-8'))
            self.assertEqual(len(grid['features']),1849)
            self.assertTrue(any(f['properties']['rain_mean_mm_h']==0 for f in grid['features']))
            self.assertTrue(any(f['properties']['rain_mean_mm_h'] is None for f in grid['features']))
            self.assertTrue(all(0<=f['properties']['rain_valid_pct']<=100 for f in grid['features']))
            for k in ['courses','steep']:
                fc=json.loads((root/'dist'/record['assets'][k]).read_text('utf-8'))
                self.assertEqual(len(fc['features']),6 if k=='courses' else 55)
                self.assertTrue(all(f['properties']['frame_id']==record['frame_id'] for f in fc['features']))
            # Test the actual console synchronizer using a minimal headless canvas.
            class Canvas:
                def freeze(self,*a):pass
                def refresh(self):pass
            class Interface:
                def mapCanvas(self):return Canvas()
            project=QgsProject.instance();project.clear();project.setFileName(str(root/'qgis/test.qgs'))
            scope={'iface':Interface()};exec((p.ROOT/'qgis/sync_layers.py').read_text('utf-8'),scope)
            self.assertEqual(len(project.mapLayers()),3)
            self.assertEqual(scope['hallasan_frame_id'],record['frame_id']);scope['hallasan_radar_timer'].stop();project.clear()
            # A contradictory same-time revision must not replace the published pointer.
            m['verification_note']='modified metadata';p.atomic_json(mp,m)
            with self.assertRaises(ValueError):p.ingest(mp,root)
            self.assertEqual(json.loads((root/'dist/state/latest.json').read_text())['frame_id'],record['frame_id'])

if __name__=='__main__':unittest.main(verbosity=2)
