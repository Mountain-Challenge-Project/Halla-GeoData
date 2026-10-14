"""Build the Jeju Olle course layer from the OSM downloads and summarise terrain slope along each course.

Inputs : work/public_sources/osm_olle_relations.json, osm_olle_ways.json (fetch_olle_routes.py)
         outputs/jeju_slope/slope_degrees_30m.tif (build_slope_data.py with SLOPE_REGION=jeju)
Outputs: inputs/reference/jeju_olle_routes.gpkg          layer olle_routes (EPSG:4326)
         outputs/jeju_slope/shapefiles/reference_olle.shp (EPSG:32652, for the QGIS project)
         outputs/jeju_slope/jeju_olle_summary.csv          per-course length and slope summary
         outputs/jeju_slope/olle_coverage.json             which official courses OSM provides

Course codes are parsed from OSM names/refs (올레길 3A, JOT14, Ollegil 10, 제주올레길 10-1 ...) and
normalised to the official style: 1, 1-1, 3-A, 14-1, 15-B. A course comes from its route relation
when OSM has one; otherwise from highway ways whose name carries the course number.
Slope summary: the slope raster is sampled every 10 m along the course (each sample stands for 10 m),
a coarser method than the exact pixel split used for the Hallasan courses. © OpenStreetMap contributors, ODbL.
"""
from pathlib import Path
import csv, json, math, re, sys
import numpy as np
from osgeo import gdal, ogr, osr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT, load

gdal.UseExceptions(); ogr.UseExceptions(); osr.UseExceptions()
cfg = load('jeju')
OUT = ROOT / cfg['output_dir']; SHAPES = OUT / 'shapefiles'
SRC = ROOT / 'work' / 'public_sources'
relations = json.loads((SRC / 'osm_olle_relations.json').read_text('utf-8'))['elements']
ways = json.loads((SRC / 'osm_olle_ways.json').read_text('utf-8'))['elements']
OFFICIAL = ['1', '1-1', '2', '3-A', '3-B', '4', '5', '6', '7', '7-1', '8', '9', '10', '10-1', '11', '12', '13', '14', '14-1',
            '15-A', '15-B', '16', '17', '18', '18-1', '19', '20', '21']
CODE = re.compile(r'(?:올레\s*길?|olle(?:gil)?(?:\s*trail)?|JOT)\s*(\d{1,2})\s*(?:코스)?\s*(?:[-–‐]?\s*(\d)\b|\s*\(?\s*-?\s*([AB])\b\)?)?', re.I)


def course_code(tags):
    for key in ('ref', 'name', 'name:ko', 'name:en'):
        value = tags.get(key, '')
        m = CODE.search(value)
        if m:
            base, sub, letter = m.group(1), m.group(2), m.group(3)
            if sub: return f'{int(base)}-{sub}'
            if letter: return f'{int(base)}-{letter.upper()}'
            return str(int(base))
    return None


def variant(tags):
    text = ' '.join(str(v) for v in tags.values()).lower()
    return 'wheelchair' if 'wheelchair' in text or '휠체어' in text else ''


WGS = osr.SpatialReference(); WGS.ImportFromEPSG(4326); WGS.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
UTM = osr.SpatialReference(); UTM.ImportFromEPSG(32652); UTM.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
to_utm = osr.CoordinateTransformation(WGS, UTM)


def line(coords):
    g = ogr.Geometry(ogr.wkbLineString)
    for p in coords: g.AddPoint_2D(p['lon'], p['lat'])
    return g


courses = {}  # key: (code, variant) -> record
member_ways = set()
for rel in relations:
    tags = rel.get('tags', {}); code = course_code(tags)
    geoms = [line(m['geometry']) for m in rel.get('members', []) if m['type'] == 'way' and m.get('geometry')]
    if not code or not geoms:
        print('skipped relation', rel['id'], tags.get('name', ''), '| code', code, '| ways', len(geoms)); continue
    member_ways.update(m['ref'] for m in rel.get('members', []) if m['type'] == 'way')
    rec = courses.setdefault((code, variant(tags)), {'code': code, 'variant': variant(tags), 'names': [], 'relations': [], 'ways': 0, 'geoms': [], 'kind': set()})
    rec['names'].append(tags.get('name') or tags.get('ref') or ''); rec['relations'].append(rel['id']); rec['ways'] += len(geoms); rec['geoms'] += geoms; rec['kind'].add('relation')
for way in ways:
    tags = way.get('tags', {}); code = course_code(tags)
    if not code or way['id'] in member_ways or not way.get('geometry'):
        continue
    key = (code, variant(tags))
    if key in courses and 'relation' in courses[key]['kind']:
        continue  # the relation already defines this course; loose named ways would duplicate it
    rec = courses.setdefault(key, {'code': code, 'variant': variant(tags), 'names': [], 'relations': [], 'ways': 0, 'geoms': [], 'kind': set()})
    if tags.get('name') and tags['name'] not in rec['names']: rec['names'].append(tags['name'])
    rec['ways'] += 1; rec['geoms'].append(line(way['geometry'])); rec['kind'].add('named_ways')


def sort_key(code):
    parts = code.split('-'); return (int(parts[0]), parts[1] if len(parts) > 1 else '')


# Slope sampling along each course from the Jeju slope raster (UTM 52N, 30 m).
ras = gdal.Open(str(OUT / 'slope_degrees_30m.tif')); band = ras.GetRasterBand(1); arr = band.ReadAsArray(); gt = ras.GetGeoTransform(); nodata = band.GetNoDataValue()
H, W = arr.shape


def sample(geom_utm, step=10.0):
    values = []
    for part in ([geom_utm] if geom_utm.GetGeometryName() == 'LINESTRING' else list(geom_utm)):
        length = part.Length()
        n = max(1, int(length // step))
        for i in range(n + 1):
            d = min(length, i * step)
            p = part.Value(d) if hasattr(part, 'Value') else None
            if p is None: continue
            c = int((p.GetX() - gt[0]) / gt[1]); r = int((p.GetY() - gt[3]) / gt[5])
            if 0 <= r < H and 0 <= c < W and arr[r, c] != nodata and arr[r, c] >= 0:
                values.append(float(arr[r, c]))
    return np.array(values)


records = []
for key in sorted(courses, key=lambda k: (sort_key(k[0]), k[1])):
    rec = courses[key]
    multi = ogr.Geometry(ogr.wkbMultiLineString)
    for g in rec['geoms']: multi.AddGeometry(g)
    merged = multi.Clone()
    utm = merged.Clone(); utm.Transform(to_utm)
    length_m = utm.Length()
    v = sample(utm)
    steep = float((v >= 20).sum() * 10.0) if v.size else 0.0
    row = {'course': rec['code'], 'variant': rec['variant'], 'name_osm': rec['names'][0] if rec['names'] else '', 'source_kind': '+'.join(sorted(rec['kind'])),
           'osm_relations': ','.join(map(str, rec['relations'])), 'ways': rec['ways'], 'length_km': round(length_m / 1000, 3),
           'samples_10m': int(v.size), 'mean_deg': round(float(v.mean()), 2) if v.size else None, 'p90_deg': round(float(np.percentile(v, 90)), 2) if v.size else None,
           'max_deg': round(float(v.max()), 2) if v.size else None, 'steep20_m': round(steep, 1), 'steep20_pct': round(steep / length_m * 100, 2) if length_m else None,
           'geom': merged, 'geom_utm': utm}
    records.append(row)

# GeoPackage (WGS84) for inputs/reference
gpkg = ROOT / 'inputs/reference/jeju_olle_routes.gpkg'
drv = ogr.GetDriverByName('GPKG')
if gpkg.exists(): drv.DeleteDataSource(str(gpkg))
ds = drv.CreateDataSource(str(gpkg)); layer = ds.CreateLayer('olle_routes', WGS, ogr.wkbMultiLineString)
fields = [('course', ogr.OFTString), ('variant', ogr.OFTString), ('name_osm', ogr.OFTString), ('source_kind', ogr.OFTString), ('osm_relations', ogr.OFTString), ('ways', ogr.OFTInteger),
          ('length_km', ogr.OFTReal), ('samples_10m', ogr.OFTInteger), ('mean_deg', ogr.OFTReal), ('p90_deg', ogr.OFTReal), ('max_deg', ogr.OFTReal), ('steep20_m', ogr.OFTReal), ('steep20_pct', ogr.OFTReal), ('source', ogr.OFTString), ('notice', ogr.OFTString)]
for n, k in fields: layer.CreateField(ogr.FieldDefn(n, k))
SOURCE_TEXT = '© OpenStreetMap contributors, ODbL 1.0; Overpass API download, see work/public_sources/download_manifest.json'
NOTICE = 'OSM 기반 참고 선형. 공식 제주올레 코스 선형·현재 개방 상태 미검증. 경사는 10m 간격 표본의 지형 경사이며 보행 경사가 아님.'
for row in records:
    f = ogr.Feature(layer.GetLayerDefn()); f.SetGeometry(row['geom'])
    for n, _ in fields:
        value = {'source': SOURCE_TEXT, 'notice': NOTICE}.get(n, row.get(n))
        if value is not None: f.SetField(n, value)
    layer.CreateFeature(f)
ds = None

# Shapefile (UTM 52N) for the QGIS project; short field names.
shp = SHAPES / 'reference_olle.shp'
sdrv = ogr.GetDriverByName('ESRI Shapefile')
if shp.exists(): sdrv.DeleteDataSource(str(shp))
sds = sdrv.CreateDataSource(str(shp)); slayer = sds.CreateLayer('reference_olle', UTM, ogr.wkbMultiLineString, options=['ENCODING=UTF-8'])
sfields = [('course', ogr.OFTString, 10), ('variant', ogr.OFTString, 12), ('name', ogr.OFTString, 60), ('src', ogr.OFTString, 20), ('osm_rel', ogr.OFTString, 60), ('ways', ogr.OFTInteger, 0),
           ('len_km', ogr.OFTReal, 0), ('mean_deg', ogr.OFTReal, 0), ('p90_deg', ogr.OFTReal, 0), ('max_deg', ogr.OFTReal, 0), ('steep20_m', ogr.OFTReal, 0), ('steep20pct', ogr.OFTReal, 0)]
for n, k, w in sfields:
    fd = ogr.FieldDefn(n, k)
    if w: fd.SetWidth(w)
    if k == ogr.OFTReal: fd.SetWidth(18); fd.SetPrecision(3)
    slayer.CreateField(fd)
mapping = {'name': 'name_osm', 'src': 'source_kind', 'osm_rel': 'osm_relations', 'len_km': 'length_km', 'steep20pct': 'steep20_pct'}
for row in records:
    f = ogr.Feature(slayer.GetLayerDefn()); f.SetGeometry(row['geom_utm'])
    for n, _, _ in sfields:
        value = row.get(mapping.get(n, n))
        if value is not None: f.SetField(n, value)
    slayer.CreateFeature(f)
sds = None

with (OUT / 'jeju_olle_summary.csv').open('w', encoding='utf-8-sig', newline='') as fh:
    cols = ['course', 'variant', 'name_osm', 'source_kind', 'osm_relations', 'ways', 'length_km', 'samples_10m', 'mean_deg', 'p90_deg', 'max_deg', 'steep20_m', 'steep20_pct']
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
    for row in records: w.writerow({k: row[k] for k in cols})
present = sorted({r['course'] for r in records}, key=sort_key)
coverage = {'official_courses': OFFICIAL, 'present_in_osm': present, 'missing_in_osm': [c for c in OFFICIAL if c not in present],
            'extra_codes': [c for c in present if c not in OFFICIAL], 'features': len(records),
            'from_relations': sorted({r['course'] for r in records if 'relation' in r['source_kind']}, key=sort_key),
            'from_named_ways_only': sorted({r['course'] for r in records if r['source_kind'] == 'named_ways'}, key=sort_key),
            'total_length_km': round(sum(r['length_km'] for r in records), 1), 'method': 'OSM Overpass download; course code parsed from name/ref; slope sampled every 10 m from slope_degrees_30m.tif',
            'licence': 'ODbL 1.0, © OpenStreetMap contributors', 'official_geometry_verified': False}
(OUT / 'olle_coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in coverage.items() if k != 'official_courses'}, ensure_ascii=False, indent=1))
for row in records:
    print(f"{row['course']:>5} {row['variant']:<10} {row['source_kind']:<18} ways {row['ways']:>3}  {row['length_km']:>7.2f} km  mean {row['mean_deg']}  max {row['max_deg']}  >=20deg {row['steep20_m']} m  | {row['name_osm']}")
