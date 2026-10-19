"""PRIMARY (1순위) forest structure: 산림청 임상도 1:5,000 SHP -> per-cell forest type / age / density (QGIS Python; run here).

Download from https://map.forest.go.kr (login), unzip, set FGIS_FOREST_SHP in .env to the folder or one .shp.
Samples a 50 m lattice per 500 m cell and writes Geo Data Analyst/data/jeju_grid_forest.csv with
  forest_share (% of samples inside a forest polygon), conifer_pct / broadleaf_pct / mixed_pct (of forest samples),
  age_class_mean (영급), density_mode (소/중/밀 -> 1/2/3), height_class_mean (수고 급, when present)
Field names differ between editions; the candidates below cover the common ones. These columns are added to grid.geojson by
update_grid_properties.py when the file exists (forest_share, conifer_pct, broadleaf_pct, age_class_mean, density_mode).
"""
import os, csv, json, sys, glob
os.environ['QT_QPA_PLATFORM'] = 'offscreen'; os.environ.setdefault('SHAPE_ENCODING', 'CP949')
from pathlib import Path
import numpy as np
from osgeo import ogr, osr
ogr.UseExceptions()
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]; GDA = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'work')); from env_config import env_value  # noqa: E402
TYPE_FIELDS = ['FRTP_CD', 'FRTP_NM', 'STORUNST', 'KOFTR_GROU']; AGE_FIELDS = ['AGCLS_CD', 'AGCLS', 'AGE_CLS']; DEN_FIELDS = ['DNST_CD', 'DNST', 'DENSITY']; HGT_FIELDS = ['HEIGHT', 'HGHT_CD', 'HEIGHT_CLS']
DENSITY_LETTERS = {'A': 1, 'B': 2, 'C': 3}   # 소/중/밀 in the 2021 edition


def field(ly, cands):
    return next((f for f in cands if ly.GetLayerDefn().GetFieldIndex(f) >= 0), None)


def main():
    src = env_value('FGIS_FOREST_SHP')
    if not src or not Path(src).exists(): print('FGIS_FOREST_SHP가 비어 있거나 경로가 없습니다. 산림공간정보서비스에서 제주 임상도를 내려받아 경로를 .env에 적으세요.'); return 2
    shps = [src] if src.lower().endswith('.shp') else sorted(glob.glob(str(Path(src) / '**/*.shp'), recursive=True))
    wgs = osr.SpatialReference(); wgs.ImportFromEPSG(4326); wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    layers = []
    for p in shps:
        ds = ogr.Open(p); ly = ds.GetLayer(); srs = ly.GetSpatialRef(); srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        layers.append((ds, ly, osr.CoordinateTransformation(wgs, srs), field(ly, TYPE_FIELDS), field(ly, AGE_FIELDS), field(ly, DEN_FIELDS), field(ly, HGT_FIELDS)))
    grid = json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8')); rows = []
    for f in grid['features']:
        ring = np.array(f['geometry']['coordinates'][0]); lon0, lat0, lon1, lat1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
        xs = np.linspace(lon0, lon1, 11)[:-1] + (lon1 - lon0) / 20; ys = np.linspace(lat0, lat1, 11)[:-1] + (lat1 - lat0) / 20
        n = 0; types = {'conifer': 0, 'broadleaf': 0, 'mixed': 0}; ages = []; dens = []; hgts = []
        for x in xs:
            for y in ys:
                for ds, ly, tr, tf, af, df, hf in layers:
                    pt = ogr.Geometry(ogr.wkbPoint); pt.AddPoint_2D(float(x), float(y)); pt.Transform(tr); ly.SetSpatialFilter(pt); feat = next(iter(ly), None); ly.SetSpatialFilter(None)
                    if feat is None: continue
                    n += 1; t = str(feat.GetField(tf) or '') if tf else ''
                    if t.startswith('1') or '침엽' in t: types['conifer'] += 1
                    elif t.startswith('2') or '활엽' in t: types['broadleaf'] += 1
                    elif t.startswith('3') or '혼효' in t: types['mixed'] += 1
                    for fld, acc in ((af, ages), (df, dens), (hf, hgts)):
                        if fld:
                            raw = feat.GetField(fld); raw = DENSITY_LETTERS.get(str(raw).strip().upper(), raw) if fld == df else raw
                            try: acc.append(float(str(raw).strip('급')))
                            except (TypeError, ValueError): pass
                    break
        tot = max(1, sum(types.values()))
        rows.append({'grid_id': f['properties']['grid_id'], 'forest_share': round(100.0 * n / 100, 1), 'conifer_pct': round(100 * types['conifer'] / tot, 1), 'broadleaf_pct': round(100 * types['broadleaf'] / tot, 1), 'mixed_pct': round(100 * types['mixed'] / tot, 1),
                     'age_class_mean': round(sum(ages) / len(ages), 2) if ages else '', 'density_mode': max(set(dens), key=dens.count) if dens else '', 'height_class_mean': round(sum(hgts) / len(hgts), 2) if hgts else ''})
    out = GDA / 'data/jeju_grid_forest.csv'
    with out.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('FGIS_FOREST_IMPORTED', {'cells': len(rows), 'sheets': len(layers), 'forest_cells': sum(1 for r in rows if r['forest_share'] >= 50)})
    print('다음: python work/update_grid_properties.py 로 grid.geojson에 결합')


if __name__ == '__main__':
    sys.exit(main())
