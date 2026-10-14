"""Turn a collected KMA radar PCPH ASCII file into a verified GeoTIFF, run the existing
Hallasan frame pipeline (processor.ingest), and aggregate the same raster onto the Jeju-wide grid.

Run with QGIS Python:
  "C:\\Program Files\\QGIS 4.2.0\\bin\\python-qgis.bat" -X utf8 work/radar_to_frame.py [--raw FILE] [--no-ingest]

Inputs
  runtime/kma/raw/PCPH_MSK_MM_60min_<tm>_<hash>.txt (+ .json)   kma_client.py fetch output
  runtime/kma/latlon/rdr_latlon_PCP_{lon,lat}.bin                nph-rdr_latlon_api cmp=PCP disp=B
                                                                  (4-byte header, then nx*ny little-endian float32,
                                                                  x fastest, south to north, same order as the ASCII)
  outputs/jeju_dashboard/data/grid.geojson                        Jeju 500 m cells (WGS84)
  outputs/jeju_slope/shapefiles/study_boundary.shp                Jeju boundary (UTM 52N)
Outputs
  work/public_sources/kma_radar_grid.json                         verified grid definition (CRS, numbering, errors)
  outputs/hallasan_radar_layers_v1/input/KMA_PCPH60_<tm>.{tif,json}   verified rain-rate GeoTIFF + metadata
  outputs/hallasan_radar_layers_v1/dist/frames/<id>/..., state/latest.json  via processor.ingest (Hallasan grid)
  runtime/kma/frames/<id>/jeju_frame.json, db_latest.json, db_frame.json, db_part_NNN.json
  outputs/jeju_dashboard/data/latest_frame.json                   Jeju-grid frame for the dashboard

Grid verification (2026-10-15): the official lon/lat arrays place cell (i, j) at
((i-1121)*500, (j-1681)*500) m in a Lambert conformal conic with standard parallels 30/60, origin 126E/38N,
on the WGS84 ELLIPSOID (max 0.8 m over a nationwide lattice and every Jeju cell). The spherical LCC the
repository's reference grids assumed (R=6371008.77 m) puts the same cell numbers about 1.06 km too far
south at Jeju, so those polygons are geographic references with radar-cell ids, not the radar cells
themselves; rain is aggregated onto them by geographic overlap. Unit: PCPH acc=60 unit=MM gives mm*100
accumulated over the preceding 60 minutes, numerically the hourly mean rain rate in mm/h; -25000 (no echo)
is a valid 0, -30000 (outside radar range) and every other negative code are nodata.
"""
from pathlib import Path
import argparse, datetime as dt, hashlib, json, struct, sys
import numpy as np
from osgeo import gdal, ogr, osr

ROOT = Path(__file__).resolve().parent.parent
RADAR = ROOT / 'outputs' / 'hallasan_radar_layers_v1'
sys.path.insert(0, str(RADAR))
import processor as p  # noqa: E402  (QGIS-based aggregation, unchanged)

I0, J0, SIZE = 1121, 1681, 500
OFFICIAL_PROJ4 = '+proj=lcc +lat_1=30 +lat_2=60 +lat_0=38 +lon_0=126 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs'
GRID_TOLERANCE_M = 5.0
KST = dt.timezone(dt.timedelta(hours=9))
DOC = 'https://apihub.kma.go.kr/apiList.do?seqApi=5'
osr.UseExceptions(); gdal.UseExceptions(); ogr.UseExceptions()


def parse_ascii(path, dtype):
    lines = [l for l in Path(path).read_text('utf-8', 'replace').splitlines() if l.strip() and not l.startswith('#')]
    nx, ny = [int(v) for v in lines[0].replace('=', '').split(',') if v.strip()]
    values = np.fromstring(','.join(l.replace('=', '').strip(', ') for l in lines[1:]), sep=',', dtype=dtype)
    if values.size != nx * ny:
        raise SystemExit(f'{path}: {values.size} values, expected {nx * ny} (file truncated?)')
    return nx, ny, values.reshape(ny, nx)  # row 0 = south, x fastest


def load_bin(path, nx, ny):
    data = Path(path).read_bytes()
    arr = np.frombuffer(data[4:], dtype='<f4')
    if arr.size != nx * ny:
        raise SystemExit(f'{path}: {arr.size} floats, expected {nx * ny}')
    return arr.reshape(ny, nx).astype(np.float64)


def official_srs():
    s = osr.SpatialReference(); s.ImportFromProj4(OFFICIAL_PROJ4); s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER); return s


def assumed_srs():
    ds = ogr.Open(str(ROOT / 'inputs/reference/hallasan_course_cells.gpkg'))
    s = ds.GetLayerByName('candidate_lcc_grid_500m').GetSpatialRef().Clone(); s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER); return s


def grid_errors(lon, lat, srs, rows, cols):
    wgs = osr.SpatialReference(); wgs.ImportFromEPSG(4326); wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(wgs, srs)
    rr, cc = np.meshgrid(list(rows), list(cols), indexing='ij'); rr = rr.ravel(); cc = cc.ravel()
    pts = np.array(tr.TransformPoints(list(zip(lon[rr, cc], lat[rr, cc]))))[:, :2]
    e = np.hypot(pts[:, 0] - (cc + 1 - I0) * SIZE, pts[:, 1] - (rr + 1 - J0) * SIZE)
    return {'cells': int(e.size), 'max_m': round(float(e.max()), 2), 'mean_m': round(float(e.mean()), 2), 'p95_m': round(float(np.percentile(e, 95)), 2)}


def verify_grid(lon, lat):
    ny, nx = lat.shape
    samples = {'jeju_window': (range(633, 716), range(1149, 1296)), 'nationwide_lattice': (range(0, ny, 96), range(0, nx, 96)), 'corners': ([0, ny - 1], [0, nx - 1])}
    report = {'grid': {'nx': nx, 'ny': ny, 'cell_m': SIZE, 'reference_cell_1based': [I0, J0], 'order': 'x fastest, south to north; cell centre = ((i-i0)*500, (j-j0)*500)'},
              'official_crs_proj4': OFFICIAL_PROJ4, 'official': {k: grid_errors(lon, lat, official_srs(), *v) for k, v in samples.items()},
              'repository_assumed_spherical_lcc': {k: grid_errors(lon, lat, assumed_srs(), *v) for k, v in samples.items()},
              'reference_cell_lonlat': [float(lon[J0 - 1, I0 - 1]), float(lat[J0 - 1, I0 - 1])], 'tolerance_m': GRID_TOLERANCE_M}
    report['passed'] = all(report['official'][k]['max_m'] <= GRID_TOLERANCE_M for k in samples)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', help='raw PCPH ASCII (default: newest in runtime/kma/raw)')
    ap.add_argument('--no-ingest', action='store_true', help='skip processor.ingest (Hallasan frame)')
    args = ap.parse_args()
    raw = Path(args.raw) if args.raw else sorted((ROOT / 'runtime/kma/raw').glob('PCPH_*.txt'))[-1]
    manifest = json.loads(raw.with_suffix('.json').read_text('utf-8'))
    params = manifest['parameters_without_key']
    if params.get('cmp') != 'PCPH' or params.get('unit') != 'MM' or int(params.get('acc', 0)) != 60:
        raise SystemExit('this converter handles PCPH, unit=MM, acc=60 only; got ' + json.dumps(params))
    tm = manifest['requested_at_kst']
    observed = dt.datetime.strptime(tm, '%Y%m%d%H%M').replace(tzinfo=KST).astimezone(dt.timezone.utc)

    # 1. raw values and the official grid coordinates
    nx, ny, a = parse_ascii(raw, np.int32)
    lon = load_bin(ROOT / 'runtime/kma/latlon/rdr_latlon_PCP_lon.bin', nx, ny); lat = load_bin(ROOT / 'runtime/kma/latlon/rdr_latlon_PCP_lat.bin', nx, ny)
    report = verify_grid(lon, lat)
    print('GRID_VERIFICATION', json.dumps(report), flush=True)
    if not report['passed']:
        raise SystemExit('official grid does not match the LCC/WGS84 definition within tolerance; not converting')
    latlon_manifest = json.loads((ROOT / 'runtime/kma/latlon/manifest.json').read_text('utf-8')) if (ROOT / 'runtime/kma/latlon/manifest.json').exists() else {}
    grid_def = {**report, 'verified_on': dt.date.today().isoformat(), 'source_api': 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-rdr_latlon_api?cmp=PCP&latlon={lon,lat}&disp=B',
                'source_files': {k: v for k, v in latlon_manifest.items() if k.endswith('.bin')}, 'implication': 'Reference grids in inputs/reference/radar_grid_cells.gpkg are generated with official_crs_proj4, so cell ids match radar cells; the earlier spherical-LCC grids (candidate_lcc_grid_500m) sat about 1.06 km south of the true cells at Jeju.'}
    (ROOT / 'work/public_sources/kma_radar_grid.json').write_text(json.dumps(grid_def, ensure_ascii=False, indent=2), encoding='utf-8')

    # 2. raw values -> mm/h float GeoTIFF in the official CRS
    rate = np.full(a.shape, -9999.0, dtype=np.float32)
    rate[a >= 0] = a[a >= 0] * 0.01
    rate[a == -25000] = 0.0
    codes = {int(k): int(v) for k, v in zip(*np.unique(a[a < 0], return_counts=True))}
    out_dir = RADAR / 'input'; out_dir.mkdir(exist_ok=True)
    tif = out_dir / f'KMA_PCPH60_{tm}.tif'
    ds = gdal.GetDriverByName('GTiff').Create(str(tif), nx, ny, 1, gdal.GDT_Float32, options=['COMPRESS=DEFLATE', 'TILED=YES'])
    ds.SetGeoTransform(((1 - I0) * SIZE - SIZE / 2, SIZE, 0, (ny - J0) * SIZE + SIZE / 2, 0, -SIZE))
    ds.SetProjection(official_srs().ExportToWkt())
    band = ds.GetRasterBand(1); band.SetNoDataValue(-9999.0); band.WriteArray(rate[::-1, :]); band.SetUnitType('mm/h'); ds.FlushCache(); ds = None
    off = report['repository_assumed_spherical_lcc']['jeju_window']
    note = (f'격자: 공식 nph-rdr_latlon_api(cmp=PCP, disp=B) 경위도 {nx}x{ny}를 LCC(표준위선 30/60, 원점 126E/38N, WGS84 타원체)로 투영하면 셀 중심이 ((i-{I0}),(j-{J0}))*500 m와 '
            f'최대 {report["official"]["nationwide_lattice"]["max_m"]} m(전국 격자), {report["official"]["jeju_window"]["max_m"]} m(제주 창) 안에서 일치. '
            f'참고격자(radar_grid_cells.gpkg)는 같은 정의로 생성되어 셀 ID가 레이더 셀과 일치하며, 집계는 참고격자 폴리곤과 레이더 픽셀의 지리적 겹침으로 수행(이전 구면 LCC 격자는 제주에서 평균 {off["mean_m"]} m 어긋났음). '
            f'행 순서: ASCII 남→북을 북→남으로 뒤집어 저장. 단위: PCPH acc=60 unit=MM 값×0.01 = 직전 60분 누적 mm = 1시간 평균 강우강도 mm/h. '
            f'결측: -25000(에코 없음)=유효 0, 그 외 음수 코드 {json.dumps({k: v for k, v in codes.items() if k != -25000})}는 nodata(-9999).')
    meta = {'raster': tif.name, 'observed_at': observed.isoformat().replace('+00:00', 'Z'), 'source_product': 'KMA API Hub nph-rdr_cmp1_api cmp=PCPH qcd=MSK obs=ECHO acc=60 map=HB disp=A unit=MM',
            'source_reference': DOC, 'quantity': 'rain_rate', 'unit': 'mm/h', 'value_encoding': 'physical_float', 'grid_verified': True, 'unit_verified': True, 'nodata_verified': True,
            'verification_note': note, 'revision': 0, 'accumulation_minutes': 60,
            'accumulation_window_kst': [(observed.astimezone(KST) - dt.timedelta(minutes=60)).strftime('%Y-%m-%d %H:%M'), observed.astimezone(KST).strftime('%Y-%m-%d %H:%M')],
            'raw_file': raw.name, 'raw_sha256': manifest['sha256'], 'negative_code_counts': codes, 'grid_verification': report, 'converted_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    (out_dir / f'KMA_PCPH60_{tm}.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print('GEOTIFF_WRITTEN', tif.name, 'valid px', int((rate >= 0).sum()), 'rain px', int((rate > 0).sum()), 'max mm/h', round(float(rate.max()), 2), flush=True)

    # 3. Hallasan frame through the unchanged pipeline
    if not args.no_ingest:
        result = p.ingest(out_dir / f'KMA_PCPH60_{tm}.json', RADAR)
        frame_id = result['frame_id']
        print('HALLASAN_FRAME', frame_id, 'valid native pixels', result['valid_native_pixels'], flush=True)
    else:
        p.init(); frame_id = observed.strftime('%Y%m%dT%H%M%SZ') + '-r0-' + manifest['sha256'][:16]

    # 4. Jeju-wide aggregation with the same functions
    from qgis.core import QgsGeometry
    bds = ogr.Open(str(ROOT / 'outputs/jeju_slope/shapefiles/study_boundary.shp')); bf = next(iter(bds.GetLayer(0)))
    boundary = QgsGeometry(); boundary.fromWkb(bytes(bf.GetGeometryRef().ExportToWkb()))
    d, pixels, window = p.crop_pixels(tif, boundary)
    grid_fc = json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8'))
    geoms, index = p.features_in_utm(grid_fc)
    stats = p.aggregate(geoms, index, pixels)
    cells = {}
    for f, s in zip(grid_fc['features'], stats):
        if s['rain_mean_mm_h'] is None:
            continue
        cells[f['properties']['grid_id']] = [round(s['rain_mean_mm_h'], 3), round(s['rain_max_mm_h'], 3) if s['rain_max_mm_h'] is not None else None, round(s['rain_valid_pct'], 1)]
    means = [v[0] for v in cells.values()]
    summary = {'cells_total': len(grid_fc['features']), 'cells_with_data': len(cells), 'cells_rain_gt0': sum(1 for m in means if m > 0), 'max_mean_mm_h': max(means) if means else None,
               'native_pixels_in_boundary': len(pixels), 'note': f'기상청 레이더 PCPH 60분 누적 환산 1시간 평균 강우강도 · 관측 {observed.astimezone(KST).strftime("%m-%d %H:%M")} KST'}
    frame = {'schema_version': 1, 'frame_id': frame_id, 'observed_at': meta['observed_at'], 'published_at': p.stamp(), 'unit': 'mm/h', 'quantity': 'rain_rate',
             'source_product': meta['source_product'], 'accumulation_minutes': 60, 'revision': 0, 'summary': summary, 'cells': cells}
    fdir = ROOT / 'runtime/kma/frames' / frame_id; fdir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(frame, ensure_ascii=False, separators=(',', ':'))
    (fdir / 'jeju_frame.json').write_text(text, encoding='utf-8')
    (ROOT / 'outputs/jeju_dashboard/data/latest_frame.json').write_text(text, encoding='utf-8')
    items = sorted(cells.items()); size = 1500; parts = max(1, (len(items) + size - 1) // size)
    for i in range(parts):
        (fdir / f'db_part_{i:03d}.json').write_text(json.dumps({'v': dict(items[i * size:(i + 1) * size]), 'part': i}, separators=(',', ':')), encoding='utf-8')
    head = {k: frame[k] for k in ['frame_id', 'observed_at', 'published_at', 'unit', 'quantity', 'source_product', 'revision', 'accumulation_minutes', 'summary']}
    (fdir / 'db_frame.json').write_text(json.dumps({**head, 'parts': parts, 'cells': len(cells)}, ensure_ascii=False, indent=1), encoding='utf-8')
    (fdir / 'db_latest.json').write_text(json.dumps({'status': 'available', 'frame_id': frame_id, 'observed_at': meta['observed_at'], 'published_at': frame['published_at'], 'message': summary['note'], 'parts': parts, 'cells': len(cells), 'unit': 'mm/h', 'poll_seconds': 60}, ensure_ascii=False, indent=1), encoding='utf-8')
    print('JEJU_FRAME', json.dumps({'frame_id': frame_id, 'dir': str(fdir), 'db_parts': parts, **summary}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
