"""Write outputs/jeju_slope/START_HERE.html: what the ZIP contains, how to open it in QGIS,
what each layer shows, how to style polygons/grid/rasters/Olle courses, and every field's meaning.
Plain Python; reads the bundle's CSV/JSON files only.
"""
from pathlib import Path
import csv, html, json, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT, load

cfg = load('jeju'); OUT = ROOT / cfg['output_dir']
validation = json.loads((OUT / 'validation.json').read_text('utf-8'))
metadata = json.loads((OUT / 'metadata.json').read_text('utf-8'))
classes = validation['classes']
fields = list(csv.DictReader((OUT / 'field_dictionary.csv').open(encoding='utf-8-sig')))
olle = list(csv.DictReader((OUT / 'jeju_olle_summary.csv').open(encoding='utf-8-sig'))) if (OUT / 'jeju_olle_summary.csv').exists() else []
coverage = json.loads((OUT / 'olle_coverage.json').read_text('utf-8')) if (OUT / 'olle_coverage.json').exists() else {}
colours = ['#ffffff', '#fcffb8', '#fff158', '#ffd800', '#ffab09', '#ff7826', '#f53b22', '#d20000', '#a40000', '#7c0014']
e = html.escape
grid_n = validation['grid_count']


def table(headers, rows):
    head = ''.join(f'<th>{e(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


class_rows = [[f'<span class="chip" style="background:{colours[i]}"></span>', f"{c['min_deg']}–{c['max_deg'] if c['max_deg'] < 90 else '90'}°", f"{c['area_m2']/1e6:,.1f}", f"{c['area_pct']:.2f}"] for i, c in enumerate(classes)]
olle_rows = [[e(r['course']), e(r['variant'] or ''), e(r['name_osm']), e(r['source_kind']), r['length_km'], r['mean_deg'], r['p90_deg'], r['max_deg'], r['steep20_m'], r['steep20_pct']] for r in olle]
field_rows = [[f"<code>{e(r['field'])}</code>", e(r['meaning'])] for r in fields]
olle_fields = [('course', '올레 코스 번호(공식 표기: 1, 1-1, 3-A, 14-1 …). OSM 이름·ref에서 해석'), ('variant', "변형 선형. 'wheelchair'는 OSM의 휠체어 대체 선형"), ('name / name_osm', 'OSM에 기록된 이름'),
               ('src / source_kind', "relation = OSM 루트 릴레이션, named_ways = 릴레이션 없이 이름만 붙은 길"), ('osm_rel / osm_relations', 'OSM 릴레이션 ID'), ('ways', '선형을 이루는 OSM way 수'),
               ('len_km / length_km', 'UTM 52N 평면 길이 km'), ('samples_10m', '경사 표본 수(10 m 간격)'), ('mean_deg', '표본 평균 지형 경사각 °'), ('p90_deg', '표본 90백분위 경사각 °'), ('max_deg', '표본 최대 경사각 °'),
               ('steep20_m / steep20pct', '20° 이상 표본 수 × 10 m 와 그 길이 비율 %. 분석용 기준이며 공식 난이도 아님')]
layers = [
    ('배경: Esri 위성·항공영상', 'satellite_background.tif', '래스터 (EPSG:3857)', '제주 범위 Esri World Imagery 내보내기. 표시용이며 분석에 쓰지 않음', '켜짐'),
    ('경사 등급: Copernicus 30m / Horn', 'shapefiles/slope_classes.shp', f"폴리곤 {validation['slope_polygon_count']:,}개", '30 m 경사각을 5° 간격 10등급으로 나눈 연속 폴리곤. class_id로 색을 입힘', '켜짐 (투명도 62%)'),
    (f'제주 전역 500m 참고격자 · 통계 {grid_n:,}개', 'shapefiles/grid_slope_500m.shp', f'폴리곤 {grid_n:,}개', '격자별 평균·90백분위·최대 경사, 고도, 경사향, 등급별 면적비율. 단계구분도의 기본 자료', '켜짐 (외곽선만)'),
    ('탐방로 참고 선형 · OSM 6코스', 'shapefiles/reference_trails.shp', '선 6개', '한라산 탐방로(어리목·영실·성판악·관음사·돈내코·어승생악) OSM 선형', '켜짐'),
    ('제주올레 코스 · OSM 참고 선형', 'shapefiles/reference_olle.shp', f'선 {len(olle)}개', '제주올레 코스 OSM 선형과 코스별 경사 요약. 코스 번호 라벨', '켜짐') if olle else None,
    ('분석 범위: 제주 외곽선과 겹치는 LCC 격자', 'shapefiles/study_boundary.shp', '멀티폴리곤 1개', '선택된 격자의 합집합. 래스터와 등급 폴리곤은 이 범위로 잘림', '켜짐 (외곽선만)'),
    ('국립공원 참고 경계', 'shapefiles/reference_park.shp', '폴리곤 1개', '한라산국립공원 OSM 참고 경계', '꺼짐'),
    ('기존 지명 참고점', 'shapefiles/reference_labels.shp', '점 9개', '한라산 주변 지명 참고점', '꺼짐'),
    ('경사각 래스터 (도)', 'slope_degrees_30m.tif', '래스터 30 m (EPSG:32652)', 'GDAL Horn 경사각. 폴리곤·격자 통계의 원천', '꺼짐'),
    ('고도 DSM (m)', 'dem_30m.tif', '래스터 30 m', 'Copernicus GLO-30을 UTM 52N 30 m로 재투영한 표면 고도', '꺼짐'),
    ('경사향 래스터 (도)', 'aspect_degrees_30m.tif', '래스터 30 m', '사면 방향 (북 0°, 동 90°, 남 180°, 서 270°)', '꺼짐'),
]
layer_rows = [[e(a), f'<code>{e(b)}</code>', e(c), e(d), e(f)] for a, b, c, d, f in layers if a]
tree = '''jeju_slope/
├─ START_HERE.html              ← 이 안내
├─ jeju_slope.qgs               ← QGIS 프로젝트 (모든 레이어·색상·라벨 포함, 상대경로)
├─ jeju_slope_satellite.png     ← 완성 지도 이미지 (2834×2740)
├─ jeju_grid_slope.csv          ← 격자 7,519행 통계 (SHP 속성과 동일 값)
├─ jeju_slope_classes.csv       ← 10개 등급별 면적
├─ jeju_olle_summary.csv        ← 올레 코스별 길이·경사 요약
├─ olle_coverage.json           ← OSM에 있는/없는 올레 코스 목록
├─ field_dictionary.csv         ← 격자 칼럼 사전
├─ metadata.json                ← 출처·방법·한계 전체 기록
├─ validation.json / delivery_validation.json ← 검증 결과
├─ dem_30m.tif · slope_degrees_30m.tif · aspect_degrees_30m.tif ← 30 m 래스터
├─ satellite_background.tif     ← 배경영상 (지오레퍼런스된 JPEG-in-TIFF)
└─ shapefiles/
   ├─ grid_slope_500m.shp/.shx/.dbf/.prj/.cpg + .qml   ← 격자 + 저장된 스타일
   ├─ slope_classes.*  + .qml                           ← 등급 폴리곤
   ├─ reference_olle.* + .qml                           ← 올레 코스
   ├─ reference_trails.* · reference_park.* · reference_labels.* + .qml
   └─ study_boundary.* + .qml'''
missing = ', '.join(coverage.get('missing_in_osm', [])) or '없음'
named_only = ', '.join(coverage.get('from_named_ways_only', [])) or '없음'
page = f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>제주도 전역 경사 자료 · QGIS 사용 안내</title>
<style>body{{margin:0;background:#f2f4ef;color:#20342f;font:16px/1.75 "Malgun Gothic",sans-serif}}main{{max-width:1100px;margin:auto;padding:45px 32px 90px}}h1{{font-size:34px;line-height:1.4}}h2{{margin-top:58px;border-top:2px solid #c7d5cb;padding-top:24px;font-size:24px}}h3{{margin-top:28px}}a{{color:#067469}}nav{{display:flex;gap:18px;flex-wrap:wrap;border-bottom:1px solid #bfcbc3;padding:15px 0}}.card{{background:white;border:1px solid #d5ded6;border-radius:12px;padding:20px 25px;margin:20px 0}}.note{{border-left:5px solid #b65a2c;padding:12px 20px;background:#fff6e9}}table{{border-collapse:collapse;width:100%;background:white;font-size:14px}}td,th{{border-bottom:1px solid #d9e1db;padding:10px 13px;text-align:left;vertical-align:top}}th{{background:#dae9e1;white-space:nowrap}}.scroll{{overflow-x:auto}}code{{font-family:Consolas,monospace;font-size:13px;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;word-break:break-all;padding:18px;background:#183d36;color:#e5f8ed;border-radius:8px}}img{{max-width:100%;border:1px solid #bbc9bf}}.chip{{display:inline-block;width:65px;height:24px;border:1px solid #c4ccc4}}details{{background:white;border:1px solid #d0dcd3;margin:10px 0;padding:12px 16px}}summary{{cursor:pointer;font-weight:bold}}li{{margin:8px 0}}.muted{{color:#526a60}}.flow{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.flow div{{background:#dfece3;padding:20px;border-radius:10px}}@media(max-width:700px){{main{{padding:20px}}.flow{{display:block}}}}@media print{{nav{{display:none}}details{{break-inside:avoid}}body{{background:white}}}}</style>
<main><p class="muted">JEJU / TERRAIN · 작성 {e(metadata['created'])}</p><h1>제주도 전역 500m 격자 경사 자료<br>ZIP 구조 · QGIS 레이어 · 폴리곤 시각화 안내</h1>
<p>ZIP을 푼 뒤 <a href="jeju_slope.qgs">jeju_slope.qgs</a>를 QGIS의 <b>프로젝트 → 열기</b>로 여세요. 색상·라벨·레이어 순서가 모두 저장되어 있어 바로 아래 지도가 나타납니다. QGIS 4.2.0에서 확인했습니다.</p>
<nav><a href="#result">결과 요약</a><a href="#open">ZIP 풀기·열기</a><a href="#structure">폴더 구조</a><a href="#layers">레이어 설명</a><a href="#viz">폴리곤·격자·래스터 시각화</a><a href="#olle">올레 코스</a><a href="#fields">칼럼 사전</a><a href="#limits">출처·한계</a></nav>

<section id="result"><h2>1. 결과 요약</h2>
<p>제주 외곽선과 겹치는 500 m 격자 <b>{grid_n:,}개</b>(한라산 기존 1,849개 포함)에 Copernicus GLO-30 DSM으로 계산한 30 m 경사각을 집계했습니다. 면적 가중 평균 경사 <b>{validation['overall_mean_slope_degrees']:.2f}°</b>, 최대 <b>{validation['maximum_slope_degrees']:.1f}°</b>, 고도 범위 {validation['elevation_range_m'][0]:.0f}–{validation['elevation_range_m'][1]:.0f} m, 등급 폴리곤 {validation['slope_polygon_count']:,}개입니다.</p>
<h3>경사 등급별 면적</h3>{table(['색', '등급', '면적 km²', '비율 %'], class_rows)}
<img src="jeju_slope_satellite.png" alt="제주도 전역 500m 격자 경사도 지도">
<div class="note"><b>여기서 경사는 DSM 표면의 지형 경사입니다.</b> 나무·건물이 포함된 표면 모델이며 보행 경사나 공식 위험등급이 아닙니다. 해안 격자에는 바다 픽셀(고도 약 0 m, 경사 0°)이 포함되어 평균이 낮아집니다. 격자는 가정 LCC 좌표계이며 기상청 공식 격자와의 정렬은 검증되지 않았습니다.</div></section>

<section id="open"><h2>2. ZIP을 푼 다음 무엇을 열어야 하나요?</h2><ol>
<li><code>jeju_slope_QGIS_SHP.zip</code>을 <b>한 폴더에 통째로</b> 풉니다. 폴더 이름과 파일 위치를 바꾸지 마세요. 프로젝트가 상대경로로 파일을 찾습니다.</li>
<li>QGIS에서 <b>프로젝트 → 열기 → jeju_slope.qgs</b>를 선택합니다. SHP 하나만 드래그하면 스타일 없이 열립니다.</li>
<li>레이어 패널의 체크박스로 래스터·공원 경계·지명을 켜고 끌 수 있습니다. 어떤 레이어가 '찾을 수 없음'으로 뜨면 ZIP이 부분적으로 풀린 것이니 다시 푸세요.</li>
<li>인쇄용 지도는 <b>프로젝트 → 레이아웃 관리자 → 제주도 전역 경사도 위성지도</b>에 저장되어 있습니다. PNG·PDF로 다시 내보낼 수 있습니다.</li>
<li>SHP만 다른 프로젝트에서 쓰려면 같은 이름의 <code>.qml</code>을 <b>레이어 속성 → 스타일 → 스타일 불러오기</b>로 적용하면 같은 색이 됩니다.</li></ol></section>

<section id="structure"><h2>3. 폴더 구조</h2><pre>{e(tree)}</pre>
<p>SHP는 <code>.shp</code>(도형) <code>.shx</code>(색인) <code>.dbf</code>(속성) <code>.prj</code>(좌표계) <code>.cpg</code>(UTF-8 인코딩) 다섯 파일이 한 세트입니다. <code>.qml</code>은 QGIS 스타일 파일로 데이터가 아니라 색상·라벨 정의만 담습니다. 좌표계는 벡터·분석 래스터가 EPSG:32652(UTM 52N), 배경영상이 EPSG:3857이며 프로젝트가 즉시 변환합니다.</p></section>

<section id="layers"><h2>4. 모든 레이어의 역할</h2>{table(['프로젝트의 레이어 이름', '파일', '도형·개수', '내용', '기본 표시'], layer_rows)}</section>

<section id="viz"><h2>5. 폴리곤·격자·래스터 시각화 방법</h2>
<h3>A. 경사 등급 폴리곤 (slope_classes)</h3>
<p>저장된 스타일은 <b>범주화(Categorized)</b> 렌더러로 <code>class_id</code> 1–10에 아래 색을 대응시키고 투명도를 62%로 두어 위성영상이 비치게 합니다. 직접 만들려면 레이어 속성 → 심볼 → 범주화 → 값 <code>class_id</code> → 분류 → 각 범주 색을 지정합니다. 등급 경계(5° 간격)를 유지해야 한라산 번들과 색 의미가 같습니다.</p>
<p>{''.join(f'<span class="chip" style="background:{c}" title="{i*5}–{(i+1)*5}°"></span>' for i, c in enumerate(colours))}</p>
<p>특정 등급만 보려면 레이어 속성 → 소스 → 피처 필터(쿼리 작성기)에 <code>"class_id" &gt;= 5</code>(20° 이상)처럼 입력합니다. 면적이 큰 폴리곤부터 찾으려면 속성표에서 <code>area_m2</code>를 내림차순 정렬합니다.</p>
<h3>B. 500 m 격자 단계구분도 (grid_slope_500m)</h3>
<p>저장된 스타일은 외곽선만 그립니다. 격자를 색으로 채우려면 <b>단계구분(Graduated)</b> 렌더러에서 값 <code>mean_deg</code>(평균) 또는 <code>max_deg</code>(최대), <code>p90_deg</code>(90백분위)를 고르고 모드를 '동일 간격' 또는 '자연 분류(Jenks)'로 5–7단계 나눕니다. 제주 전역은 0–5°가 66%라서 '분위수' 모드는 평지 안의 작은 차이를 과장하므로 비교 목적이면 <b>고정 구간(0, 2, 5, 10, 15, 20, 30°)</b>을 권합니다. 투명도 40–50%를 주면 영상과 함께 읽기 쉽습니다.</p>
<p>등급별 면적비율 칼럼(<code>p00_05</code> … <code>p45_plus</code>)으로 "급경사 비율이 높은 격자"를 찾을 수 있습니다. 예: 필터 <code>"p20_25" + "p25_30" + "p30_35" + "p35_40" + "p40_45" + "p45_plus" &gt;= 20</code>. 한라산 기존 격자만 보려면 <code>inputs/reference/jeju_grid_cells.gpkg</code>의 <code>in_hallasan</code> 필드를 조인하거나 <code>"i_ref" BETWEEN 1202 AND 1244 AND "j_ref" BETWEEN 651 AND 693</code>을 사용합니다.</p>
<h3>C. 래스터 (slope_degrees_30m · dem_30m · aspect_degrees_30m)</h3>
<p>레이어 속성 → 심볼 → 렌더 유형 <b>단일밴드 의사색상</b>, 보간 '이산', 최소 0 최대 45, 색상표 'Spectral' 반전 또는 위 10색을 5° 간격으로 추가하면 폴리곤 등급과 같은 그림이 됩니다. 값 -9999는 NoData로 등록되어 있어 투명하게 처리됩니다. DSM은 '음영기복도(Hillshade)' 렌더 유형으로 바꾸면 지형감을 더합니다. 경사향은 0–360° 순환 색상표(예: 'Cyclic')가 적합합니다.</p>
<h3>D. 라벨·순서·투명도</h3>
<p>레이어 순서는 위에서부터 올레 코스 → 탐방로 → 분석 범위 → 격자 → 등급 폴리곤 → 배경영상입니다. 폴리곤을 격자 위로 올리면 격자선이 가려지므로 순서를 유지하세요. 탐방로와 올레 코스는 선을 따라 이름·코스번호 라벨이 붙어 있으며 라벨 패널에서 글꼴 크기(현재 9pt·8pt)를 바꿀 수 있습니다.</p></section>

<section id="olle"><h2>6. 제주올레 코스 레이어</h2>
<p>OSM(OpenStreetMap)의 제주올레 루트 릴레이션과, 릴레이션 없이 이름만 붙은 길(way)을 코스 번호로 묶어 만들었습니다. 총 {len(olle)}개 선형, {coverage.get('total_length_km', 0)} km입니다. OSM에 없는 공식 코스: <b>{e(missing)}</b>. 이름 붙은 길로만 복원한 코스(끊김·누락 가능): <b>{e(named_only)}</b>.</p>
{table(['코스', '변형', 'OSM 이름', '출처', '길이 km', '평균 °', '90% °', '최대 °', '20° 이상 m', '비율 %'], olle_rows) if olle else '<p>올레 요약 파일이 없습니다.</p>'}
<div class="note">코스별 경사는 선형을 따라 <b>10 m 간격으로 경사 래스터를 표본화</b>한 값입니다(표본 1개 = 10 m). 한라산 6코스 분석(outputs/hallasan_course_slope_v2)의 정확한 픽셀 분할 방식보다 거친 추정이며, 길의 진행 방향 경사가 아니라 그 지점 지형의 최대 경사입니다. OSM 선형은 공식 제주올레 경로·우회로·현재 개방 상태와 다를 수 있습니다.</div>
<p>시각화: <code>reference_olle</code> 레이어를 단계구분 렌더러로 <code>mean_deg</code>에 따라 색을 바꾸거나, 필터 <code>"course" IN ('7','8','9')</code>처럼 코스를 골라 볼 수 있습니다. 속성표의 <code>steep20_m</code>이 큰 코스부터 정렬하면 급경사가 많은 코스를 찾습니다.</p></section>

<section id="fields"><h2>7. 칼럼 사전</h2><h3>grid_slope_500m.shp · jeju_grid_slope.csv</h3>{table(['칼럼', '의미'], field_rows)}
<h3>slope_classes.shp</h3>{table(['칼럼', '의미'], [['<code>poly_id</code>', '폴리곤 일련번호'], ['<code>class_id</code>', '경사 등급 1–10 (1 = 0–5°, 10 = 45° 이상)'], ['<code>deg_lo</code> / <code>deg_hi</code>', '등급 하한·상한 °'], ['<code>class_txt</code>', '등급 문자열'], ['<code>area_m2</code>', 'UTM 평면 면적 m²'], ['<code>source</code>', '고도 원자료']])}
<h3>reference_olle.shp · jeju_olle_summary.csv</h3>{table(['칼럼', '의미'], [[f'<code>{e(a)}</code>', e(b)] for a, b in olle_fields])}
<h3>study_boundary.shp</h3>{table(['칼럼', '의미'], [['<code>name</code>', '분석 범위 이름'], ['<code>area_m2</code>', 'UTM 평면 면적 m²']])}
<p>SHP 칼럼 이름은 10자 제한으로 축약되어 있고 CSV에는 전체 이름이 있습니다. CSV와 SHP의 값은 같습니다(검증: <code>delivery_validation.json</code>).</p></section>

<section id="limits"><h2>8. 출처·방법·한계</h2><ul>
<li>고도: Copernicus GLO-30 DSM 타일 N33/E126 (2021 AWS 배포본). produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.</li>
<li>배경: Esri World Imagery (Esri, Vantor, Earthstar Geographics, GIS User Community). 촬영 시기가 섞인 모자이크이며 표시용입니다.</li>
<li>격자: 한라산 격자와 같은 가정 LCC(표준위선 30°/60°, R=6371008.77 m, 기준셀 i0=1121/j0=1681). Natural Earth 1:10m 제주 외곽선(퍼블릭 도메인)과 겹치는 셀만 선택해 소축척 해안선의 한계를 그대로 가집니다.</li>
<li>탐방로·올레·공원·지명: © OpenStreetMap contributors, ODbL. 완전성·최신성 미검증.</li>
<li>방법: UTM 52N 30 m 쌍선형 재투영 → GDAL Horn 경사 → 격자별 정확한 교차면적 가중 통계. 등급 폴리곤은 셀 합집합 안의 픽셀로 잘라 바다 바깥을 제외했습니다. 상세는 <code>metadata.json</code>, 검증은 <code>validation.json</code>.</li>
<li>이 자료는 탐방 통제·안전 판단·공식 난이도를 대신하지 않습니다.</li></ul></section>
</main></html>'''
(OUT / 'START_HERE.html').write_text(page, encoding='utf-8')
print('GUIDE_WRITTEN', OUT / 'START_HERE.html', len(page), 'bytes')
