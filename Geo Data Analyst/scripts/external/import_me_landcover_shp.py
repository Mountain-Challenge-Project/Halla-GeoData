"""PRIMARY (1순위) land cover: 환경부 세분류 토지피복도 SHP -> per-cell class shares (QGIS Python; run from this folder).

The SHP cannot be fetched by script (https://egis.me.go.kr needs an interactive login). Download the Jeju sheets, unzip
them into one folder, and put that folder (or one .shp) in .env as ME_LANDCOVER_SHP. This script dissolves the sheets
into the same categories the WorldCover fallback uses (tree, shrub, grass, crop, builtup, bare, water, wetland) by the
세분류 code (L1 digit: 1 시가화 -> builtup, 2 농업 -> crop, 3 산림 -> tree, 4 초지 -> grass, 5 습지 -> wetland, 6 나지 -> bare,
7 수역 -> water), samples a 50 m lattice per 500 m cell and OVERWRITES Geo Data Analyst/data/jeju_grid_landcover.csv
with the same column names, so update_grid_properties.py and the models pick it up unchanged. A copy of the fallback
result is kept as jeju_grid_landcover_worldcover.csv.
"""
import os, csv, json, sys, glob, shutil
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import numpy as np
from osgeo import ogr, osr
ogr.UseExceptions()
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]; GDA = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'work')); from env_config import env_value  # noqa: E402
CODE_TO_CLASS = {'1': 'builtup', '2': 'crop', '3': 'tree', '4': 'grass', '5': 'wetland', '6': 'bare', '7': 'water'}
CLASSES = ['tree', 'shrub', 'grass', 'crop', 'builtup', 'bare', 'snow', 'water', 'wetland', 'mangrove', 'moss']
CODE_FIELDS = ['L3_CODE', 'L2_CODE', 'L1_CODE', 'UCB', 'CODE']   # candidate attribute names across editions


def main():
    src = env_value('ME_LANDCOVER_SHP')
    if not src or not Path(src).exists(): print('ME_LANDCOVER_SHP가 비어 있거나 경로가 없습니다. 환경공간정보서비스에서 제주 세분류 토지피복도를 내려받아 압축을 푼 폴더 경로를 .env에 적으세요.'); return 2
    shps = [src] if src.lower().endswith('.shp') else sorted(glob.glob(str(Path(src) / '**/*.shp'), recursive=True))
    if not shps: print('SHP 파일이 없습니다:', src); return 2
    wgs = osr.SpatialReference(); wgs.ImportFromEPSG(4326); wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    layers = []
    for p in shps:
        ds = ogr.Open(p); ly = ds.GetLayer(); srs = ly.GetSpatialRef(); srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        fld = next((f for f in CODE_FIELDS if ly.GetLayerDefn().GetFieldIndex(f) >= 0), None)
        if not fld: print('분류 코드 필드를 찾지 못함:', p); continue
        layers.append((ds, ly, osr.CoordinateTransformation(wgs, srs), fld))
    grid = json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8')); rows = []
    for f in grid['features']:
        ring = np.array(f['geometry']['coordinates'][0]); lon0, lat0, lon1, lat1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
        xs = np.linspace(lon0, lon1, 11)[:-1] + (lon1 - lon0) / 20; ys = np.linspace(lat0, lat1, 11)[:-1] + (lat1 - lat0) / 20
        counts = {c: 0 for c in CLASSES}; n = 0
        for x in xs:
            for y in ys:
                hit = None
                for ds, ly, tr, fld in layers:
                    pt = ogr.Geometry(ogr.wkbPoint); pt.AddPoint_2D(float(x), float(y)); pt.Transform(tr); ly.SetSpatialFilter(pt)
                    for feat in ly:
                        code = str(feat.GetField(fld) or ''); hit = CODE_TO_CLASS.get(code[:1]); break
                    ly.SetSpatialFilter(None)
                    if hit: break
                if hit: counts[hit] += 1; n += 1
        row = {'grid_id': f['properties']['grid_id'], 'n_samples': n}
        for c in CLASSES: row[f'lc_{c}'] = round(100.0 * counts[c] / n, 1) if n else 0.0
        row['canopy_mean_m'] = ''; row['canopy_p90_m'] = ''   # canopy height stays from the ETH fallback / 임상도 importer
        rows.append(row)
    out = GDA / 'data/jeju_grid_landcover.csv'
    if out.exists() and not (GDA / 'data/jeju_grid_landcover_worldcover.csv').exists(): shutil.copyfile(out, GDA / 'data/jeju_grid_landcover_worldcover.csv')
    # keep canopy columns from the previous file
    prev = {r['grid_id']: r for r in csv.DictReader((GDA / 'data/jeju_grid_landcover_worldcover.csv').open(encoding='utf-8'))} if (GDA / 'data/jeju_grid_landcover_worldcover.csv').exists() else {}
    for r in rows:
        if r['grid_id'] in prev: r['canopy_mean_m'] = prev[r['grid_id']].get('canopy_mean_m', ''); r['canopy_p90_m'] = prev[r['grid_id']].get('canopy_p90_m', '')
    with out.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('ME_LANDCOVER_IMPORTED', {'cells': len(rows), 'sheets': len(layers), 'cells_with_samples': sum(1 for r in rows if r['n_samples'])})
    print('다음: python work/update_grid_properties.py 로 grid.geojson에 결합')


if __name__ == '__main__':
    sys.exit(main())
