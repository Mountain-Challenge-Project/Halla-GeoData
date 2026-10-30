// 제주 소지역 국지기상 모델 구현·검증 보고서 (실데이터 기반) — docx-js
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, AlignmentType,
  ImageRun, LevelFormat, ShadingType, BorderStyle, TableOfContents, PageBreak, PageNumber, Footer, VerticalAlign,
} = require('docx');

const HERE = __dirname;
const FIG = path.join(HERE, 'figures', 'report_20261030');
const OUT = process.argv[2] || path.join(HERE, '제주_소지역_국지기상_모델_실데이터_보고서.docx');
const FONT = { ascii: 'Malgun Gothic', eastAsia: 'Malgun Gothic', hAnsi: 'Malgun Gothic', cs: 'Malgun Gothic' };
const TABLE_W = 9300; // DXA, fits A4 with 0.9 in margins
const IMG_W_PX = 560;  // ~5.8 in

// ── helpers ──────────────────────────────────────────────────────────
function runs(text, opts = {}) {
  // **bold** 마크업만 지원
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((p) => p.startsWith('**') ? new TextRun({ text: p.slice(2, -2), bold: true, ...opts }) : new TextRun({ text: p, ...opts }));
}
const P = (text, o = {}) => new Paragraph({ children: runs(text, o.run || {}), spacing: { after: 120, line: 300 }, alignment: o.align, ...o.par });
const H1 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 } });
const H2 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_2, spacing: { before: 280, after: 120 } });
const H3 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 100 } });
let numInstance = 0;
const bullets = (items) => items.map((t) => new Paragraph({ children: runs(t), numbering: { reference: 'bul', level: 0 }, spacing: { after: 60, line: 290 } }));
function numbered(items) { numInstance += 1; return items.map((t) => new Paragraph({ children: runs(t), numbering: { reference: 'num', level: 0, instance: numInstance }, spacing: { after: 60, line: 290 } })); }
const note = (t) => new Paragraph({ children: runs(t, { size: 17, color: '555555' }), spacing: { after: 160, line: 260 } });
const caption = (t) => new Paragraph({ children: runs(t, { size: 17, color: '333333' }), alignment: AlignmentType.CENTER, spacing: { before: 60, after: 240, line: 260 } });

function pngSize(file) { const b = fs.readFileSync(file); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; }
function figure(file, cap, widthPx = IMG_W_PX) {
  const { w, h } = pngSize(file);
  const width = Math.min(widthPx, IMG_W_PX); const height = Math.round(width * h / w);
  return [
    new Paragraph({ children: [new ImageRun({ type: 'png', data: fs.readFileSync(file), transformation: { width, height } })], alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 }, keepNext: true }),
    caption(cap),
  ];
}

const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
const borders = { top: border, bottom: border, left: border, right: border };
function cell(text, width, opts = {}) {
  const paras = Array.isArray(text) ? text : [text];
  return new TableCell({
    width: { size: width, type: WidthType.DXA }, borders, verticalAlign: VerticalAlign.CENTER,
    shading: opts.head ? { type: ShadingType.CLEAR, fill: 'E8EEF6', color: 'auto' } : (opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill, color: 'auto' } : undefined),
    margins: { top: 50, bottom: 50, left: 80, right: 80 },
    children: paras.map((t) => new Paragraph({ children: runs(t, { size: 17, bold: !!opts.head }), spacing: { after: 0, line: 250 }, alignment: opts.align })),
  });
}
function table(header, rows, widths) {
  const scale = TABLE_W / widths.reduce((a, b) => a + b, 0);
  const W = widths.map((w) => Math.round(w * scale));
  return new Table({
    width: { size: TABLE_W, type: WidthType.DXA }, columnWidths: W,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, W[i], { head: true })) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, W[i])) })),
    ],
  });
}
const gap = () => new Paragraph({ text: '', spacing: { after: 120 } });

// ── content ──────────────────────────────────────────────────────────
const body = [];
const add = (...x) => x.flat().forEach((e) => body.push(e));

add(
  new Paragraph({ children: [new TextRun({ text: '제주 소지역 국지기상 모델', bold: true, size: 44 })], alignment: AlignmentType.CENTER, spacing: { before: 2400, after: 120 } }),
  new Paragraph({ children: [new TextRun({ text: '구현·검증 보고서 — 실데이터 기반', bold: true, size: 36 })], alignment: AlignmentType.CENTER, spacing: { after: 360 } }),
  new Paragraph({ children: [new TextRun({ text: '이슬점·푄 물리 모듈, 지점 검증, 잔차 학습, 그리고 오름잇(jeju-tour) 서비스 연계', size: 24, color: '444444' })], alignment: AlignmentType.CENTER, spacing: { after: 1200 } }),
  new Paragraph({ children: [new TextRun({ text: '근거 저장소', bold: true, size: 20 })], alignment: AlignmentType.CENTER, spacing: { after: 60 } }),
  new Paragraph({ children: [new TextRun({ text: 'Mountain-Challenge-Project/Halla-GeoData (main · feat/forest-map · feat/aws-backfill · feat/my-location-rain)', size: 20 })], alignment: AlignmentType.CENTER, spacing: { after: 60 } }),
  new Paragraph({ children: [new TextRun({ text: 'jinminjoon/jeju-tour (front · feat/flutter-app)', size: 20 })], alignment: AlignmentType.CENTER, spacing: { after: 600 } }),
  new Paragraph({ children: [new TextRun({ text: '2026년 10월 30일', size: 22 })], alignment: AlignmentType.CENTER, spacing: { after: 120 } }),
  new Paragraph({ children: [new TextRun({ text: '2026-10-15 설계 보고서(제주_소지역_국지기상_모델_설계_보고서.docx)의 후속 문서. 본문 수치는 2026-10-30 22:30 KST 기준 저장소 파일·운영 API에서 읽은 값이며, 부록 C에 파일별 근거를 적었다.', size: 18, color: '555555' })], alignment: AlignmentType.CENTER }),
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({ text: '목차', heading: HeadingLevel.HEADING_1, spacing: { after: 160 } }),
  new TableOfContents('목차', { hyperlink: true, headingStyleRange: '1-2' }),
  new Paragraph({ children: [new PageBreak()] }),
);

// 요약
add(H1('요약'));
add(P('2026년 10월 15일의 설계 보고서는 제주 500 m 격자 위에 **이슬점과 푄(foehn) 현상을 중심으로 한 소지역 국지기상 모델**을 설계하고, 물리 모듈 → 잔차 학습 → 지점 검증의 3층 구조와 추가 수집 자료 목록을 제시했다. 이 보고서는 그 뒤 2주 동안 두 저장소에서 실제로 구현·수집·검증한 결과를 실데이터 수치로 정리한 것이다. 설계 보고서의 그림 2–7이 한 회차 예보의 시연이었다면, 이 보고서의 그림은 모두 관측·학습·운영 API에서 나온 값이다.'));
add(P('**구현 범위.** 설계안의 1–5단계가 모두 코드로 들어갔다. 격자는 부속섬과 해안 2 km 완충을 포함한 9,449셀로 늘었고, 정답 자료(AWS 42지점 매분, ASOS 4지점 2023년 1월부터, 산지 AWS 시간자료 소급)가 API허브에서 들어온다. 물리 모듈(이슬점·LCL·푄 단면·지점기압·체감온도·풍상 노출)은 대시보드의 색상 기준 20개와 강조 레이어로 연결됐고, 잔차 학습 모델이 전 셀에 적용돼 "학습 보정 기온/이슬점"으로 표시된다. 같은 물리 산식이 오름잇 서비스(jeju-tour)의 Express 서버에 TypeScript로 이식돼 React 웹과 Flutter 앱(웹·Android·iOS)의 "실시간 기상" 화면이 기상청 실황·예보·AWS·특보를 위성 지도 위에 보여 준다. Vercel 운영 서버는 2026-10-30 22:26 KST에 AWS 42지점 전부를 정상 응답했다.'));
add(P('**검증 결과.** 지점 검증 4회차(160행)에서 감률 보정은 5 km 원값 대비 기온 RMSE를 2.12 → 1.88 °C(11.3 % 개선)로 낮췄고, 1,000 m 이상 고지대에서는 3.58 → 2.98 °C였다. 지점기압 모듈은 ASOS 4지점 3년 13만 시간에서 RMSE 0.16–0.18 hPa였다. 푄 사례 검증(ASOS 횡단 바람 9,359시간)에서는 선별된 사례 303시간에서 공기덩이 계산이 감률 보정보다 크게 좋았으나(기온 RMSE 4.5 → 2.6 °C, 습도 27 → 16 %p), 그 밖의 9,056시간에서는 +5.1 °C 과대였다. 따라서 "응결 가능"만으로 푄을 적용하지 않고 11–16시에 30 %만 반영하는 규칙을 채택했다. 잔차 학습은 144,572행으로 재학습한 결과 지점 제외 교차검증에서 기온 RMSE 1.56(물리) → 1.40 °C(GBM), 이슬점 3.09 → 2.52 °C였다.'));
add(P('**남은 과제.** 매시 파이프라인이 2026-10-18 22:30 발표 이후 멈춰 있어 실시간 학습 행이 122개(목표 2,000)에 머물러 있고, 고지대 이슬점은 +6.5 °C의 큰 편향을 보인다. 해안 안개는 기온−이슬점 규칙만으로 정밀도 8.7 %에 그쳐 시정·천리안 산출물이 필요하지만 천리안 파일 다운로드는 아직 403이다. 환경부 세분류 토지피복도, Copernicus CDS ERA5 원자료, MODIS, Sentinel-3는 키·로그인 자리만 준비돼 있다.'));

// 1
add(H1('1. 배경과 목적'));
add(H2('1.1 설계 보고서의 요지'));
add(P('설계 보고서는 참조 논문(이보라 외, 2019)의 방법, 즉 점 관측을 정답으로 두고 격자 전역 입력과 "정답에 직접 대응하는 유도 인자"로 기계학습 모델을 학습해 공간으로 확장하는 구조를 국지기상에 옮겼다. 핵심 원칙은 다섯 가지였다. 물리 먼저·학습은 잔차, 입력 유형 분리, 선형 감률 보정을 대조군으로 유지, 셀 × 1시간 단위로 검증 가능하게 산출, 공식 예보를 대신하지 않는다는 표기.'));
add(H2('1.2 이 보고서의 범위'));
add(bullets([
  '**Halla-GeoData** 저장소의 `Geo Data Analyst/` 폴더(모델 코드·산출 JSON)와 대시보드(`work/dashboard_src`, `outputs/jeju_dashboard`)의 2026-10-30 상태. main에 병합된 커밋과 아직 PR 상태인 `feat/forest-map`(재학습), `feat/aws-backfill`(산지 AWS 소급), `feat/my-location-rain`(내 위치 강수 카드)을 포함한다.',
  '**jeju-tour** 저장소의 `front` 브랜치(실시간 기상 화면, Google Maps 전환)와 `feat/flutter-app` 브랜치(Flutter 앱), 그리고 Vercel 운영 서버(https://jeju-tour-five.vercel.app)의 응답.',
  '수치는 저장소에 커밋된 JSON·CSV와 운영 API 응답에서 그대로 옮겼고, 어떤 파일에서 왔는지 부록 C에 적었다. 설계 보고서의 산식·구조 설명은 반복하지 않고 바뀐 부분만 적는다.',
]));

// 2
add(H1('2. 시스템 구성'));
add(figure(path.join(FIG, 'figG_pipeline.png'), '그림 1. 두 저장소의 역할. 위쪽은 Halla-GeoData의 수집 → 물리 → 학습 → 대시보드 흐름, 아래쪽은 같은 물리 산식을 이식한 오름잇 서비스(Express 서버, React 웹, Flutter 앱)이다.'));
add(H2('2.1 Halla-GeoData (분석·모델)'));
add(table(['구성', '현재 상태 (2026-10-30)', '근거'], [
  ['참고격자', '공식 레이더 합성 격자(LCC 30/60, 126E/38N, WGS84 타원체) 500 m, 제주 9,449셀 = 육지 7,518 + 부속섬 136 + 해안 2 km 완충 1,795. 좌표 API 대조 최대 오차 0.78 m. 한라산 1,849셀', 'VALIDATION.json'],
  ['지형 인자', '셀별 평균·최대 경사, 고도, 경사향·집중도(GLO-30 30 m) + TPI 1 km, 하늘개방도, 해안 거리, 16방위 상류 최고고도·거리 (9,449셀 전부)', 'jeju_grid_terrain_factors.csv'],
  ['지표 인자', 'ESA WorldCover 2021 비율·ETH 수관고(차선) + 산림청 임상도 1:5,000 (폴리곤 23,986개, 침엽·활엽·혼효 비율, 영급, 밀도, 수고급; 2026-10-19 적용)', 'jeju_grid_landcover.csv, jeju_grid_forest.csv'],
  ['수집기', 'AWS 매분·ASOS 정시(`fetch_kma_obs.py`), 초단기예보·실황, KIM 925·850 hPa(`fetch_kim_levels.py`), 레이더 PCPH, 특보; 매시 `RUN_PIPELINE.cmd`, 주 1회 `RUN_TRAIN.cmd`, 매일 01:00 `RUN_BACKFILL.cmd`', 'Geo Data Analyst/scripts'],
  ['물리 모듈', '`physics_modules.py`(참조 구현) + 대시보드 자바스크립트(라이브). 이슬점·LCL·VPD, 감률 보정, 푄 단면(습윤단열 50 m 적분, 상류 능선 탐색 60 km), 정역학 지점기압, 체감온도(겨울·여름), 풍상 노출', 'compute_stage2.py'],
  ['잔차 학습', '`archive_features.py`(특징 47개) → `train_residual_model.py`(릿지·RF·GBM, 지점 제외 CV·시간 분리) → `apply_residual_model.py`(전 셀). 저장 모델 `runtime/kma/models/residual_t.joblib`, `residual_td.joblib`', 'residual_model_report.json'],
  ['대시보드', 'Leaflet, 공유 DB 동기화(radar/latest·obs·ml). 색상 기준 20개, 강조 레이어(급경사·강수, 푄 조건, 운무 가능), 셀 상세의 ±RMSE·보정량·상류 점, 내 위치 강수 카드(2026-10-28)', 'work/dashboard_src/body.html'],
], [14, 62, 24]));
add(gap());
add(P('색상 기준 20개: 평균 경사, 최대 경사, 경사향, 20° 이상 면적, 강수(평균), 3·6·24시간 누적, 예보 1시간 강수, 예보 6시간 합계, 풍상 사면 노출, 셀 추정 기온, 기온−이슬점(운무 가능), 체감온도−기온, 셀 이슬점, LCL−셀 고도, 푄 지수, 지점기압(추정), 학습 보정 기온, 학습 보정 이슬점. 설계 시점(13개)에서 7개가 늘었고 모두 설계 4.6절에서 예고한 항목이다.'));
add(H2('2.2 jeju-tour (오름잇 서비스)'));
add(table(['구성', '현재 상태', '근거'], [
  ['서버', 'Express 5 (`prototype/src/server.ts` 3,486줄) + `src/kma.ts` 261줄. 라우트 `/api/kma/status`, `/api/kma/now?lat&lon`(제주 범위 33.0–33.75 N, 125.9–127.1 E), `/api/kma/aws`, `/api/kma/warnings`. 인증키는 서버 환경변수 `KMA_API_KEY`로만 쓰고 브라우저에 내보내지 않는다. 캐시: 실황 5분, 예보 10분, AWS 3분, 특보 10분', 'front ce26760'],
  ['물리 이식', 'DFS 5 km 격자 변환(정·역변환 왕복 검증), Magnus 이슬점, 감률 6.5/2 °C/km, LCL 125 m/°C, 기상청 체감온도(겨울 JAG/TI, 여름 2022 Stull 습구), 운무 가능(기온−이슬점 ≤ 1 °C 또는 고도 ≥ LCL). 고도는 서버의 제주 DEM(`demAt`)에서 읽는다', 'src/kma.ts'],
  ['React 웹', '"실시간 기상" 메뉴(`WeatherLivePage.tsx`, `WeatherMap.tsx`): 내 위치(GPS·지도 클릭·프리셋 6곳) 실황 타일, 6시간 예보 막대, 고도 보정 카드, AWS 42지점 핀(기온 색, 강수 테두리), 한라산 8지점 묶음, 특보 배지. 지도는 2026-10-28 Leaflet → Google Maps(hybrid)로 전환', 'front 955b2d3'],
  ['Flutter 앱', '`app/` (2026-10-29, Dart 46파일 7,354줄): 같은 `/api` 봉투로 웹·Android·iOS 빌드. `weather_live_page.dart`, `widgets/maps/weather_map.dart`(google_maps_flutter 2.19), 위치는 geolocator 14.1. 웹 빌드는 Express가 `/app` 아래 같은 출처로 서비스하고, 모바일은 `--dart-define=API_BASE`로 서버를 지정', 'feat/flutter-app 29c82ab'],
  ['운영', 'Vercel 프로젝트가 포크 chaerin123/jeju-tour의 `front`를 빌드. 2026-10-30 확인: `/api/kma/status` configured = true, AWS 42/42 지점 응답, 실황·예보·특보 정상', '운영 API 응답 (7.2절)'],
], [12, 66, 22]));

// 3
add(H1('3. 확보 자료 현황'));
add(P('설계 보고서 5장의 수집 목록과 대비한 현재 상태다. 상태 표기: ● 확보·적용, ◐ 일부 또는 차선 자료, ○ 미확보.'));
add(H2('3.1 정답(학습 목표) 자료'));
add(table(['자료', '확보 상태', '양 / 범위', '비고'], [
  ['AWS 1분 (42지점)', '● 실시간', '매시 파이프라인에서 지점별 최신값 → `obs_latest.json`; 월별 CSV `runtime/kma/obs/aws_min`', '설계 시점 403 → 승인'],
  ['산지 AWS 시간자료 소급', '◐ 진행', 'API허브 매분 아카이브로 윗세오름·진달래밭·사제비·삼각봉 4지점 2026-10 → 2026-03까지 약 13,900행 (매일 01:00 2,000일-요청씩 거슬러 감)', 'feat/aws-backfill'],
  ['ASOS 시간 (제주·고산·성산·서귀포)', '●', '2023-01 ~ 2026-10, 46개월 132,711행 (로컬 아카이브)', '지점기압·푄·안개·호우 검증의 기반'],
  ['30일 고정 수집본 (2026-09-16 ~ 10-15)', '●', 'ASOS 2,880행, AWS 일통계 6,417행, 고지대 매분 102,600행(어리목·성판악 100 %, 삼각봉 17.5 %, 사제비 20 %), 고층 47186 120 프로파일 13,285층, 레이더 57,258점', 'outputs/jeju_weather/20261017 (SHA-256 매니페스트)'],
  ['라디오존데 47186 (국가태풍센터)', '●', '30일분 120 프로파일; 상시 수집은 미설정', '푄 모듈 상류 공기는 현재 KIM 850 hPa 사용'],
  ['특보', '●', '2026-10-15 첫 실응답(EUC-KR) 이후 수집; 10-30 제주 관련 0건', '사례 라벨로는 아직 미사용'],
  ['AWS 시간통계 awsh, 고층 지수, 위성 지점 운량', '○', 'HTTP 403 (2026-10-16)', '활용신청 필요'],
], [22, 11, 44, 23]));
add(gap());
add(H2('3.2 격자 전역 입력'));
add(table(['자료', '확보 상태', '내용', '비고'], [
  ['초단기예보·실황 (5 km)', '●', '제주 격자점 95개, 매시 수집. 실황은 jeju-tour 서버에서도 직접 호출', '설계 시점 실황 ○ → ●'],
  ['KIM 국지모델 925·850 hPa', '●', '기온·습도·바람을 5 km 격자점으로 집계 (`runtime/kma/kim`, 6시간마다)', '설계의 LDAPS 자리; 승인된 KIM으로 대체'],
  ['레이더 PCPH 60·180·360·1440분', '●', '500 m 셀 집계, 대시보드 강수·누적', '프레임 아카이브'],
  ['천리안 2A 안개·구름', '○', '목록 조회는 승인, 파일 다운로드는 2026-10-19 403', '별도 활용신청 필요'],
  ['ERA5·ERA5-Land', '◐ 차선', 'Open-Meteo 아카이브(계정 불필요)로 42지점 2023~ 지상·925/850 hPa 시간자료; 재분석 짝 학습 자료 133,791행', 'CDS 원자료(`CDS_API_KEY`) 미입력'],
  ['MODIS, Sentinel-3 SLSTR', '○', '수집 스크립트·키 자리만 준비', 'Earthdata·CDSE 계정 필요'],
  ['낙뢰, KIM 지상 2D', '○', '활용신청 대기', ''],
], [24, 11, 44, 21]));
add(gap());
add(H2('3.3 지형·지표 정적 인자'));
add(table(['자료', '상태', '내용'], [
  ['셀 고도·경사·경사향·집중도', '●', 'GLO-30 30 m에서 9,449셀 (설계 시점 7,518셀)'],
  ['TPI, 하늘개방도, 해안 거리', '●', 'QGIS Python `build_terrain_factors.py`'],
  ['16방위 상류 최고고도·거리', '●', '탐색 반경 25 km → 60 km로 확장 (해안 셀이 한라산을 보도록; 성산 서쪽 805 m → 1,519 m)'],
  ['토지피복', '◐ → ●', 'WorldCover 2021·ETH 수관고(차선) 적용 뒤, 산림청 임상도 1:5,000을 1순위로 결합(2026-10-19). 환경부 세분류 토지피복도는 포털 로그인 다운로드가 필요해 미수집(도엽 33605–33608, 33610–33614)'],
], [26, 10, 64]));

// 4
add(H1('4. 물리 모듈 구현과 지점 검증'));
add(H2('4.1 설계 대비 바뀐 점'));
add(bullets([
  '**이슬점 감률 적용.** 설계 시점의 대시보드는 이슬점을 고도에 따라 일정하게 두었으나, 2단계에서 이슬점 감률 2 °C/km를 적용하고 셀 기온을 넘지 않도록 제한했다. 색상 기준 "셀 이슬점"·"LCL − 셀 고도"가 추가됐다.',
  '**푄 단면의 습윤단열.** 상수 6 °C/km 대신 기온·기압에 따른 포화단열감률을 50 m 간격으로 적분한다. 하강 중 이슬점은 1.8 °C/km로 올리고, 응결된 수증기는 제거한다.',
  '**상류 공기.** 설계의 LDAPS 대신 승인된 KIM 국지모델 850 hPa 바람·기온·습도를 쓰고, 없으면 초단기예보 10 m 바람을 쓴다. 상류 점은 횡단 풍향의 상류 능선 거리만큼 풍상측으로 옮긴 5 km 예보점이다.',
  '**푄 적용 규칙.** 5단계 사례 검증(5장) 결과에 따라 푄 지수는 진단용으로 두고, 셀 기온·이슬점에는 11–16 KST에 푄 조건이 켜진 셀에서만 공기덩이 값 쪽으로 30 % 이동한 값을 쓴다(`FOEHN_BLEND = 0.3`, `FOEHN_HOURS = 11–16`).',
  '**체감온도.** 겨울형 JAG/TI에 더해 여름형(2022년 기상청 개정, Stull 습구온도)을 넣고, 대시보드에서는 기온과의 ± 차이로 표시한다.',
  '**신뢰 구간.** `verify_stations.py`가 고도대별 물리 추정 RMSE를 `uncertainty.json`에 쓰고 셀 상세에 "±RMSE(편향, 건수/회차)"로 보여 준다.',
]));
add(H2('4.2 첫 물리 점검 (2026-10-16 00:30 발표, 38지점)'));
add(P('설계 직후 첫 회차에서 5 km 원값을 셀에 그대로 쓴 경우와 감률 보정한 경우를 같은 분의 AWS 관측과 비교했다. 기온 RMSE는 1.96 → 1.75 °C(최대 절대오차 5.7 → 3.9 °C), 700 m 이상 8지점은 2.61 → 2.01 °C였다. 이슬점은 RMSE 5.22 °C, 편향 +1.29 °C로 고지대 예보 습도 오차가 큰 것이 확인됐고, 이것이 2단계 이후의 과제가 됐다.'));
add(H2('4.3 누적 지점 검증 (3단계)'));
add(figure(path.join(FIG, 'figB_verification_elev.png'), '그림 2. 지점 검증 누적 4회차(2026-10-17 08:30 ~ 10-18 22:30 발표, 지점 × 회차 = 160행). 왼쪽은 기온 RMSE를 5 km 원값(무보정 대조군)·감률 보정(선형 대조군)·푄 반영(2단계 물리)으로, 오른쪽은 이슬점 RMSE를 고도대별로 비교했다. 자료: verification_summary.json.'));
add(table(['구분', 'n', '기온 RMSE: 원값 → 감률 → 푄 반영 (°C)', '이슬점 RMSE (감률) · 편향 (°C)'], [
  ['전체', '160', '2.12 → 1.88 → 1.89 (원값 대비 −11.3 %)', '3.55 · +0.58'],
  ['< 300 m', '112', '1.54 → 1.42 → 1.42', '1.64 · −0.61'],
  ['300–1,000 m', '24', '2.45 → 2.30 → 2.33', '3.24 · +0.17'],
  ['≥ 1,000 m', '24', '3.58 → 2.98 → 2.97 (편향 +2.73 → +2.00)', '7.82 · +6.54'],
  ['푄 조건 활성 행', '4', '1.06 → 0.78 → 1.11', '4.45 · +2.95'],
], [18, 8, 40, 34]));
add(gap());
add(P('감률 보정의 효과는 고도가 높을수록 크고, 1,000 m 이상에서도 +2 °C의 양의 편향(예보가 더 따뜻함)이 남는다. 이슬점은 고지대에서 +6.5 °C 과대로, 5 km 예보 습도가 산지의 포화 상태를 따라가지 못한다는 설계 보고서의 우려가 수치로 드러났다. 푄 반영은 4회차·4행으로는 감률 보정과 구분되지 않으며, 이 통계가 의미를 가지려면 수 주의 누적이 필요하다. 셀 집계 사례(2026-10-18 22:30 발표 23시 값)에서는 9,449셀 중 구름 속(셀 고도 ≥ LCL) 613셀, 기온−이슬점 ≤ 1 °C 2,006셀, 푄 지수 ≥ 1 °C 944셀, 푄 조건(응결 + 바람그늘 ≥ 300 m + 횡단 풍속 ≥ 5 m/s + 지수 ≥ 1 °C) 22셀이었고, 같은 분 42지점 비교에서 기온 RMSE 1.38 °C(편향 −0.2), 이슬점 1.43 °C였다.'));
add(H2('4.4 지점기압 모듈'));
add(P('해면기압을 셀 고도로 정역학 환산하는 식을 ASOS 4지점 2023–2026년 자료로 검증했다. 층 평균기온에 가온도를 쓰면 RMSE가 건조공기 가정보다 작고, 연도별 차이가 없다.'));
add(table(['지점', '기압계 고도', 'n (시간)', '가온도: 편향 / RMSE (hPa)', '건조공기: RMSE (hPa)'], [
  ['제주 (184)', '22.0 m', '33,201', '−0.15 / 0.16', '0.17'],
  ['고산 (185)', '72.5 m', '33,096', '−0.16 / 0.16', '0.21'],
  ['성산 (188)', '21.7 m', '33,191', '−0.17 / 0.18', '0.19'],
  ['서귀포 (189)', '53.2 m', '33,213', '−0.17 / 0.18', '0.22'],
  ['윗세오름 AWS (871)', '1,675.8 m', '3', '−0.24 / 0.24', '—'],
  ['삼각봉 AWS (867)', '1,503.3 m', '3', '−0.32 / 0.34', '—'],
  ['진달래밭 AWS (870)', '1,488.6 m', '3', '0.00 / 0.22', '—'],
], [22, 14, 12, 28, 24]));
add(gap());
add(P('고지대 AWS는 3개 표본뿐이지만 0.2–0.3 hPa 안에 있어 해면기압에서 산정부 기압을 구하는 데 식 자체의 오차는 작다. 대시보드 색상 기준 "지점기압(추정)"은 ASOS 해면기압 평균과 셀 기온·이슬점으로 이 식을 적용한다.'));
add(H2('4.5 실시간 적용 사례 (2026-10-30 22:00–22:26 KST)'));
add(figure(path.join(FIG, 'figE_live_profile.png'), '그림 3. 보고서 작성 시각의 AWS 42지점 매분 관측(2026-10-30 22:26 KST, jeju-tour 운영 서버 /api/kma/aws 응답). 왼쪽은 기온과 관측소 고도, 파란 선은 제주 ASOS 값에서 6.5 °C/km로 내린 감률선. 오른쪽은 같은 시각의 상대습도. 붉은 점은 한라산 8지점.'));
add(P('같은 시각 운영 서버의 `/api/kma/now`는 윗세오름(33.3623 N, 126.5181 E)에 대해 5 km 격자점(53, 36; 대표 고도 1,345 m)의 실황 8.9 °C·습도 92 %를 받아 1,669 m 고도로 보정해 셀 기온 6.8 °C, 이슬점 6.8 °C, LCL 고도 1,499 m, "구름 속·운무 가능"을 돌려주었다. 실제 윗세오름 AWS는 2.5 °C·96.3 %였다. 보정값이 관측보다 4.3 °C 높은데, 이는 4.3절의 고지대 양의 편향(+2.0 °C)과 같은 방향이고 야간 복사냉각이 더해진 사례다. 반면 제주시(33.5141 N, 126.5297 E)는 격자점(54, 39; 83 m) 실황 16.3 °C를 20 m로 보정해 16.7 °C, 이슬점 10.7 °C, 운무 아님이었고 제주 ASOS 관측 16.5 °C와 0.2 °C 차였다.'));
add(P('그림 3에서 주목할 점은 윗세오름(1,676 m, 2.5 °C, 96 %)과 1.5 km 남짓 떨어진 한라산남벽(1,576 m, 6.6 °C, 28 %)의 차이다. 한쪽은 구름 속, 다른 쪽은 건조한 바람그늘로 기온 4 °C·습도 70 %p가 갈린다. 5 km 예보 한 점으로는 재현할 수 없는 국지 차이이며, 이것이 지점 제외 교차검증에서 산지 오차가 남는 이유이자 산지 AWS 소급 자료가 1순위인 이유다.'));

// 5
add(H1('5. 사례 검증 (5단계)'));
add(H2('5.1 푄 사례 선별'));
add(figure(path.join(FIG, 'figD_case_catalogue.png'), '그림 4. ASOS 4지점 아카이브(2023-01 ~ 2026-10, 132,711행)에서 선별한 사례 라벨의 월별 분포. 왼쪽부터 푄 후보 사례 145건, 안개 관측 2,058시간, 호우(1시간 20 mm 또는 3시간 60 mm 이상) 167시간. 자료: foehn_cases_asos_summary.json, asos_case_catalogue_summary.json.'));
add(P('동서(고산 ↔ 성산)·남북(제주 ↔ 서귀포) 지점 쌍에서 풍상 풍속 6 m/s 이상, 풍향 ±50°, 풍하 기온 +3 °C 이상, 습도 15 %p 이상 하락, 풍하 습도 70 % 이하 조건으로 후보 297시간·145건을 골랐다. 3–5월에 73건이 몰리고, 서풍 때 성산이 풍하인 경우가 104건으로 가장 많다. 가장 강한 사례는 2024-05-24 10–15시 고산 → 성산(기온차 10.8 °C, 습도차 62 %p, 풍속 7.1 m/s)이다. 해안 지점 기준 선별이므로 산지 사면의 푄은 포착하지 못한다.'));
add(H2('5.2 푄 모듈 검증과 적용 규칙'));
add(figure(path.join(FIG, 'figC_foehn_validation.png'), '그림 5. 푄 사례 검증. 풍상 ASOS 지점 공기를 지점 연결선 2 km 안의 최고 셀(약 1,921 m)을 넘겨 풍하 지점 고도로 내린 공기덩이 값을, 풍상 값 지속·감률 보정과 함께 풍하 관측과 비교했다. 왼쪽·가운데는 사례 303시간과 그 밖의 횡단 바람 9,056시간의 RMSE, 오른쪽은 사례 시간의 시각 분포와 채택한 적용 창. 자료: foehn_case_validation.json.'));
add(table(['구분', '시간', '기온 RMSE: 지속 / 감률 / 공기덩이 (°C)', '습도 RMSE: 지속 / 감률 / 공기덩이 (%p)', '공기덩이 편향'], [
  ['푄 사례', '303', '4.74 / 4.53 / **2.63**', '28.1 / 27.4 / **15.9**', '기온 +1.31 °C, 습도 −9.5 %p'],
  ['그 밖 횡단 바람', '9,056', '1.86 / 1.94 / 5.74', '10.4 / 10.5 / 35.4', '기온 **+5.09 °C**, 습도 −32 %p'],
  ['풍하 성산 (사례)', '240', '4.85 / 4.54 / 2.59', '—', '+1.41 °C'],
  ['풍하 서귀포 (사례)', '50', '4.40 / 4.59 / 2.27', '—', '+0.19 °C'],
], [20, 9, 27, 27, 17]));
add(gap());
add(P('세 가지가 확인됐다. 첫째, 사례에서는 공기덩이 모듈이 감률 보정보다 기온 RMSE를 절반 가까이 줄이고 습도도 크게 낫다. 둘째, 그러나 횡단 바람 전체의 99.8 %에서 능선이 LCL보다 높아 "응결 가능"으로 판정되므로, 그 조건만으로 공기덩이 값을 쓰면 +5.1 °C 과대가 된다. 셋째, 사례는 거의 낮 12–18시에 있고 풍상 맑음 비율이 51 %(그 밖 19 %)여서 해안 풍하 승온의 상당 부분은 일사 차이다. 푄 지수와 관측 승온의 상관은 0.096에 불과했다.'));
add(P('게이트·블렌드 탐색(시간 창 × 풍상 습도 하한 × 블렌드 비율)에서 "11–16시, 풍속 6 m/s 이상, 공기덩이 값 쪽으로 30 % 이동"이 전 시간 RMSE 2.076 → 2.008 °C로 가장 좋았고(2,717시간 적용), 이 규칙을 `physics_modules.py`와 대시보드에 반영했다. 상류 공기로 지상 ASOS 값을 쓴 검증이므로 KIM 850 hPa 상류 공기를 쓰는 라이브 산출과는 조건이 다르며, 사례 시간은 3단계 선별에 의해 기온 대비가 일부 선택된 것이어서 습도와 "그 밖 시간" 블록이 독립적인 점검이다.'));
add(H2('5.3 안개·호우 사례'));
add(bullets([
  '**안개** 2,058시간(4–7월 집중, 고산 690·제주 648·서귀포 541·성산 179). 운무 규칙(기온−이슬점 ≤ 1 °C)의 해안 지점 재현율 48.2 %, 정밀도 8.7 %. 규칙이 맞는 11,349시간 중 안개는 991시간뿐이어서 해안 이류무는 이 규칙만으로 잡기 어렵고 시정·천리안 안개 산출물이 필요하다. 산지 안개는 ASOS가 없어 평가하지 못했다.',
  '**호우**(1시간 20 mm 이상 또는 3시간 60 mm 이상) 167시간: 6월 38·9월 33시간, 성산 67·서귀포 56시간. 지형성 강수 강화 검증의 라벨로 보관하며, 레이더 셀 강수와의 결합은 아직 수행하지 않았다.',
]));

// 6
add(H1('6. 잔차 학습 모델 (4단계)'));
add(H2('6.1 학습 자료와 구성'));
add(P('학습 대상은 관측 − 물리 추정(잔차)이고 최종 추정은 물리값 + 학습 잔차다. 특징은 설계의 37개에서 47개로 늘었다. 시각·계절(3), 지점·셀·격자점 고도와 차이(4), 경사·경사향·집중도(4), TPI·하늘개방도·해안 거리(3), 상류 능선·바람그늘(2), 토지피복·수관고(6), 임상도(4: forest_share, conifer_pct, age_class_mean, density_mode), 초단기예보(8), KIM 850·925 hPa(8), 물리값(5: 감률 기온·이슬점, LCL 상대 고도, 푄 지수·조건). 실시간 행이 적어 재분석(Open-Meteo ERA5, 차선)을 예보 자리에 넣은 "재분석 짝" 자료를 함께 쓴다.'));
add(table(['항목', '첫 모델 (2026-10-18 23:00)', '재학습 (2026-10-19 11:37, feat/forest-map)'], [
  ['학습 행', '133,871 (재분석 짝 133,791 + 실시간 80)', '144,572 (재분석 짝 144,450 + 실시간 122)'],
  ['지점 구성', '해안 ASOS 4지점 각 33,000행, 산지 4지점(어리목 623, 성판악 588, 사제비 144, 삼각봉 126)', '산지 4지점(윗세오름·진달래밭·사제비·삼각봉)이 API허브 백필로 각 2,600–2,800행'],
  ['특징', '43개', '47개 (임상도 4개 추가)'],
  ['저장 임계치', '2,000행 · 20지점 · 48회차 → 통과(status ok)', '통과; 실시간 122행 < 2,000이라 "예비" 표시 유지'],
], [18, 41, 41]));
add(gap());
add(H2('6.2 결과'));
add(figure(path.join(FIG, 'figA_model_results.png'), '그림 6. 지점 제외 교차검증(GroupKFold, 42지점) RMSE. 연한 색은 첫 모델, 진한 색은 재학습. "물리만"은 감률 보정 물리값 단독, 릿지는 논문의 선형 대조군에 해당한다. 자료: residual_model_report.json (main, feat/forest-map).'));
add(table(['목표', '학습', '물리만 RMSE (편향)', '지점 제외 CV: 릿지 / RF / GBM', '시간 분리 (물리 → 저장 모델)', '저장 모델'], [
  ['기온', '첫 모델', '1.41 °C (+0.04)', '1.58 / **1.40** / 1.46', '1.47 → 1.28', 'RF'],
  ['기온', '재학습', '1.56 °C (+0.16)', '1.85 / 1.41 / **1.40**', '1.64 → 1.39', 'GBM'],
  ['이슬점', '첫 모델', '2.26 °C (+1.10)', '2.74 / 1.98 / **1.88**', '2.43 → 1.86', 'GBM'],
  ['이슬점', '재학습', '3.09 °C (+1.22)', '5.25 / 2.58 / **2.52**', '3.23 → 2.72', 'GBM'],
], [10, 10, 20, 24, 24, 12]));
add(gap());
add(P('재학습에서 물리만의 오차가 커진 것은 산지 표본이 늘어 어려운 지점의 비중이 커졌기 때문이며, 모델의 개선폭은 기온 −0.16 °C, 이슬점 −0.57 °C로 첫 모델(−0.01, −0.38)보다 커졌다. 릿지가 물리만보다 나쁜 것은 논문에서 선형 모델이 비선형 구간을 따라가지 못한 결과와 같은 방향이다. 알고리즘 간 차이(RF 대 GBM 0.01–0.06 °C)는 작고 입력 구성의 차이가 더 크다는 점도 논문의 결론과 일치한다.'));
add(figure(path.join(FIG, 'figF_importance.png'), '그림 7. 재학습 랜덤포레스트의 변수 중요도 상위 12개. 기온 잔차는 시각·계절 다음에 LCL 상대 고도·감률 이슬점·기온 같은 물리 유도 인자가, 이슬점 잔차는 계절 다음에 LCL·감률 이슬점·예보 습도가 온다. 임상도 인자는 상위 12에 들지 않았다.'));
add(P('설계에서 "EVI의 자리"로 둔 물리 유도 인자(LCL − 셀 고도, 감률 기온·이슬점)가 지형 고도 자체보다 높은 중요도를 보였다. 이슬점에서는 경사향과 경작지 비율·수관고가 뒤따른다. 모델은 `apply_residual_model.py`로 9,449셀 전부에 적용돼 `ml_cells.json`(predicted = 물리 + 잔차)에 쓰이고, 대시보드 색상 기준 "학습 보정 기온 / 이슬점"과 셀 상세의 보정량·교차검증 RMSE로 표시된다. 실시간 행이 2,000을 넘고 산지 백필이 1년치를 채우면 예비 표시를 풀고 다시 학습한다.'));

// 7
add(H1('7. 서비스 연계'));
add(H2('7.1 라이브 대시보드 (Halla-GeoData)'));
add(bullets([
  '색상 기준 20개와 강조 레이어(급경사·강수, 푄 조건, 운무 가능), 강수 이동 화살표, 특보 표시, 지점 관측 레이어(42지점 최신값).',
  '셀 상세: 감률·푄 반영 기온과 이슬점, 상류 점·능선·LCL, 고도대별 ±RMSE(편향, 건수/회차), 학습 보정량과 교차검증 RMSE.',
  '"내 위치 강수(GPS · 500 m 격자)" 카드(2026-10-28): 열람자의 GPS 위치가 속한 셀의 레이더 강도, 다음 1시간 예보, 6시간 합계, 누적·위험도, 강수 도달 예상 시간(풍향·풍속 이류), 특보를 한 칸에 요약. 따라가기·지도 중심 대체 모드.',
  '공유 DB 문서 radar/latest · radar/obs · radar/ml로 모든 열람자 화면이 동기화되며, 독립 실행 HTML 다운로드를 지원한다.',
]));
add(H2('7.2 오름잇 실시간 기상 화면 (jeju-tour)'));
add(P('설계 보고서 6.1절의 "체감온도·저체온", "운무·시정" 시나리오를 탐방객 화면으로 옮긴 것이다. 서버가 기상청 API허브를 대신 호출해 키를 숨기고, 응답을 5–10분 캐시해 API 호출을 줄인다. 2026-10-30 22:30 KST 운영 서버 확인 결과는 다음과 같다.'));
add(table(['라우트', '응답 (2026-10-30)', '내용'], [
  ['/api/kma/status', 'configured = true', 'Vercel 환경변수 `KMA_API_KEY` 등록 확인'],
  ['/api/kma/aws', 'tm 22:26, 42/42 지점 관측', '윗세오름 2.5 °C·96 %, 삼각봉 5.0 °C·풍속 4.4 m/s, 어리목 9.0 °C·일강수 7.5 mm, 제주 16.5 °C·69.6 %'],
  ['/api/kma/now (윗세오름)', '실황 22:00, 예보 21:30 발표 6시간', '격자점 8.9 °C → 1,669 m 보정 6.8 °C, 이슬점 6.8 °C, LCL 1,499 m, 운무 가능·구름 속, 체감 6.0 °C(−0.8)'],
  ['/api/kma/now (제주시)', '실황 22:00', '16.3 °C → 16.7 °C, 이슬점 10.7 °C, 기온−이슬점 6 °C, 운무 아님'],
  ['/api/kma/warnings', 'ok, 제주 관련 0건 (전체 4행)', '특보 본문은 EUC-KR 디코딩 후 위치 기반 파싱'],
], [22, 28, 50]));
add(gap());
add(P('화면은 내 위치(GPS·지도 클릭·프리셋 6곳: 백록담·윗세오름·성판악·어리목·제주시·서귀포)의 실황 타일(기온·강수·습도·바람), 6시간 예보 막대(강수량·기온·하늘), 고도 보정 카드(격자점 고도와 내 위치 고도의 차, 보정 기온·이슬점·체감온도·운무 판정), AWS 42지점 핀(기온 색 램프는 Halla-GeoData 대시보드와 동일, 강수 중이면 파란 테두리), 한라산 8지점(윗세오름·남벽·삼각봉·진달래밭·사제비·영실·어리목·성판악) 묶음 표, 특보 배지로 구성된다. 지도는 Google Maps hybrid(위성 + 지명)이며 지도 종류 전환이 가능하다.'));
add(H2('7.3 Flutter 앱 (feat/flutter-app)'));
add(P('2026-10-29에 React 화면 전체를 Dart로 옮긴 앱이 추가됐다(46파일 7,354줄). 실시간 기상은 `features/weather/weather_live_page.dart`와 `widgets/maps/weather_map.dart`가 담당하며 모델(`models/kma.dart`)은 서버의 `src/shared/types.ts`와 같은 필드다. 웹 빌드(`flutter build web --base-href /app/`)는 Express가 `/app` 아래 같은 출처로 서비스해 `/api`를 그대로 쓰고, Android·iOS는 `--dart-define=API_BASE=https://jeju-tour-five.vercel.app`로 서버를 지정한다. Google Maps 키는 웹은 서버 `/api/config`에서, Android·iOS는 각각 `key.properties`·`Secrets.xcconfig`에서 읽어 저장소에 올리지 않는다. 위치·카메라·사진 권한 문구를 매니페스트에 넣었다.'));

// 8
add(H1('8. 설계 대비 달성도'));
add(table(['설계 항목 (2026-10-15)', '설계 시점', '현재 (2026-10-30)', '근거'], [
  ['1단계: 지점 메타·셀 매핑, 수집기, 지형 파생 인자', '계획', '완료 (10-16). 42지점, TPI·SVF·해안 거리·16방위 상류 고도', 'kma_stations_jeju.csv, jeju_grid_terrain_factors.csv'],
  ['2단계: 이슬점·LCL·푄 모듈, 대시보드 표시', '계획', '완료 (10-17). KIM 850 hPa 연결, 색상 기준 3개·강조 레이어 2개', 'physics_latest.json'],
  ['3단계: 지점 검증, 선형 대조군 대비 개선', '계획', '파이프라인 가동, 4회차 160행: 기온 −11.3 %. 지점기압 0.17 hPa. 누적 중단(10-18 이후) → 재가동 필요', 'verification_summary.json, pressure_module_check.json'],
  ['4단계: RF·GBM 학습, 지점 제외 교차검증', '계획', '예비 모델 2회 학습·셀 적용. 기온 1.40 °C, 이슬점 2.52 °C (재학습)', 'residual_model_report.json, ml_cells.json'],
  ['5단계: 셀 전역 적용, 신뢰 구간, 사례 검증', '계획', '불확실성 표시, 푄 사례 145건·검증 9,359시간, 안개·호우 목록. 적용 규칙 보정(30 % 블렌드)', 'foehn_case_validation.json, uncertainty.json'],
  ['정답 자료: AWS·ASOS 3년 이상', '○ (403)', 'ASOS 3년 10개월 ●, AWS 실시간 ●, 산지 시간자료 소급 ◐(2026-03까지)', '3.1절'],
  ['LDAPS 등압면', '○', 'KIM 925·850 hPa로 대체 ●', 'fetch_kim_levels.py'],
  ['고산 라디오존데', '○', '47186 30일분 ◐; 상시 수집 미설정', 'outputs/jeju_weather/20261017'],
  ['천리안 안개·구름', '○', '○ (파일 다운로드 403)', 'external_keys_status.json'],
  ['ERA5', '○', 'Open-Meteo 차선 ●, CDS 원자료 ○', 'era5_openmeteo_manifest.json'],
  ['토지피복·임상도', '○', '임상도 ●, WorldCover ●(차선), 환경부 토지피복도 ○', 'jeju_grid_forest.csv'],
  ['대시보드 색상 기준 추가(이슬점·기압·푄·습도)', '계획', '이슬점·LCL·푄 지수·지점기압·학습 보정 ● (예측 습도는 미구현)', 'body.html'],
  ['서비스 연계', '언급 없음', 'jeju-tour 서버·웹·Flutter 앱에 실시간 기상 화면 ●', 'front, feat/flutter-app'],
], [30, 10, 38, 22]));

// 9
add(H1('9. 한계와 다음 단계'));
add(H2('9.1 한계'));
add(bullets([
  '**실시간 학습 행 부족.** 매시 파이프라인의 마지막 회차가 2026-10-18 22:30 발표(`features.csv` 122행, `stationwise.csv` 160행)여서 재분석 짝 자료가 학습의 99.9 %를 차지한다. 재분석 입력으로 학습한 잔차가 예보 입력에 그대로 옮겨진다는 보장은 없다.',
  '**고지대 이슬점 편향** +6.5 °C(≥ 1,000 m). 5 km 예보 습도가 산지 포화를 반영하지 못하며, 감률 보정만으로는 줄지 않는다.',
  '**푄 모듈은 진단용.** 공기덩이 값을 그대로 쓰면 횡단 바람 대부분에서 과대다. 해안 ASOS 쌍으로 선별한 사례는 산지 사면의 푄을 대표하지 못한다.',
  '**안개 규칙의 정밀도** 8.7 %. 시정·위성 산출물 없이는 해안 이류무를 구분할 수 없다.',
  '**5 km 계단 구조**와 지형 가림을 반영하지 않는 10 m 바람은 설계 시점과 같다. 레이더 셀 강수는 jeju-tour에 이식하지 않았다(26 MB 원자료 파싱이 서버리스에 맞지 않음).',
  '**운영 환경.** 오름잇 Vercel 프로젝트는 포크 저장소를 빌드하므로 원본 `front` 변경이 자동 반영되지 않는다. API 키는 서버 환경변수로만 두고 주기적 교체 절차를 운영 규칙에 포함해야 한다.',
  '모든 산출은 분석용이며 기상청 공식 예보·특보를 대신하지 않는다.',
]));
add(H2('9.2 다음 단계'));
add(numbered([
  '매시 `RUN_PIPELINE.cmd`를 작업 스케줄러에 다시 등록해 실시간 행을 2,000 이상 쌓고(약 3일), 예비 표시를 해제한 뒤 재학습한다. 산지 AWS 소급은 2025-10 이전으로 계속 거슬러 1년치를 채운다.',
  '고지대 이슬점: KIM 850·925 hPa 습도를 셀 이슬점의 상한으로 쓰는 규칙을 시험하고, 윗세오름·사제비 습도 100 % 시간을 운무 정답으로 삼아 재현율을 평가한다.',
  '천리안 2A 파일 다운로드 활용신청, 환경부 세분류 토지피복도(도엽 9장) 로그인 다운로드, CDS 개인 토큰 발급으로 1순위 자료를 채운다.',
  '푄 모듈을 산지 AWS 쌍(어리목 ↔ 성판악, 영실 ↔ 진달래밭)으로 다시 검증하고 블렌드 비율을 사면별로 둔다.',
  '호우 167시간과 레이더 셀 강수를 결합해 "지형성 강수 강화" 시나리오(풍상 노출 × 수증기 플럭스)를 검증한다.',
  '오름잇: Vercel 연결을 원본 저장소로 바꾸거나 포크에 동기화 절차를 두고, Flutter 앱의 실시간 기상 화면에 Halla-GeoData의 500 m 셀 산출(학습 보정 기온·운무 가능·푄 조건)을 정적 JSON으로 공급하는 경로를 추가한다.',
]));

// 부록 A
add(H1('부록 A. 산식 (설계 보고서 대비 변경·추가분)'));
add(table(['항목', '식 / 규칙', '비고'], [
  ['이슬점 (Magnus)', 'γ = ln(RH/100) + 17.62·T/(243.12 + T), Td = 243.12·γ/(17.62 − γ)', '변경 없음'],
  ['셀 기온·이슬점', 'T_cell = T_pt − 0.0065·Δh, Td_cell = min(T_cell, Td_pt − 0.002·Δh)', '이슬점에 상한 추가'],
  ['상승응결고도', 'h_LCL = h_pt + 125 m × (T − Td)', '변경 없음'],
  ['습윤단열감률', 'Γ_m(T, p) = g·(1 + L·r_s/(R_d·T)) / (c_p + L²·r_s·ε/(R_d·T²)), 50 m 간격 적분', '상수 6 °C/km 대체'],
  ['푄 하강', '능선 → 셀: 건조단열 9.8 °C/km, 이슬점 +1.8 °C/km, 응결 수증기 제거', '추가'],
  ['푄 지수·조건', '지수 = T_parcel − T_lapse; 조건 = 능선 통과 시 응결 ∧ 바람그늘 ≥ 300 m ∧ 횡단 풍속 ≥ 5 m/s ∧ 지수 ≥ 1 °C', '변경 없음'],
  ['푄 적용', 'T_out = T_lapse + 0.3·(T_parcel − T_lapse), 11 ≤ KST < 17 이고 조건 참일 때; 그 외 T_lapse', '5단계 보정으로 추가'],
  ['지점기압', 'P = P_0·exp(−g·h/(R_d·T_v)), T_v = 층 평균 가온도', '가온도 명시'],
  ['체감온도 (여름)', 'T_w(Stull) → T_app = −0.2442 + 0.55399·T_w + 0.45535·T − 0.0022·T_w² + 0.00278·T_w·T + 3.0', '추가'],
  ['최종 추정', 'X_hat = X_physics + f_RF/GBM(특징 47개), 특징에 X_physics 포함', '4단계'],
  ['신뢰 구간', '±RMSE(고도대), 지점 제외 교차검증·누적 검증에서', '5단계'],
], [18, 58, 24]));
add(gap());

// 부록 B
add(H1('부록 B. 재현 방법'));
add(P('모든 명령은 Halla-GeoData 저장소 루트에서 실행한다. 네트워크 스크립트는 시스템 Python과 `.env`의 `KMA_API_KEY`, 지형 스크립트는 QGIS Python, 학습·그림은 anaconda Python(scikit-learn, matplotlib)을 쓴다.'));
add(table(['단계', '명령 / 스크립트', '산출'], [
  ['관측·예보·KIM·물리·검증·특징 (매시)', '`Geo Data Analyst/scripts/RUN_PIPELINE.cmd`', 'obs_latest.json, physics_latest.json, verification_summary.json, uncertainty.json, features.csv'],
  ['산지 AWS 소급 (매일)', '`RUN_BACKFILL.cmd`', 'runtime/kma/obs/aws_hourly/*.csv'],
  ['재분석 짝 자료', '`fetch_era5_openmeteo.py` → `build_training_set_era5.py`', 'features_era5.csv (133,791 → 144,450행)'],
  ['학습·적용 (주 1회)', '`RUN_TRAIN.cmd` = `train_residual_model.py` + `apply_residual_model.py`', 'residual_model_report.json, runtime/kma/models/*.joblib, ml_cells.json'],
  ['지점기압 검증', '`verify_pressure_asos.py`', 'pressure_module_check.json'],
  ['푄 사례·검증', '`find_foehn_cases_asos.py`, `foehn_case_validation.py`', 'foehn_cases_asos.csv, foehn_case_validation.json'],
  ['안개·호우 목록', '`asos_case_catalogue.py`', 'fog_cases_asos.csv, heavy_rain_cases_asos.csv'],
  ['임상도 결합', '`external/import_fgis_forest_shp.py` (QGIS) → `work/update_grid_properties.py`', 'jeju_grid_forest.csv, grid.geojson'],
  ['대시보드 빌드', '`python work/build_dashboard.py <출력 폴더>`', 'index.html'],
  ['이 보고서의 그림', '`make_figs.py` (저장소 JSON + 운영 API 응답)', '그림 1–7'],
  ['오름잇 서버', '`cd prototype && npm run build && npm start`; Flutter 웹 `cd app && flutter build web --base-href /app/`', 'http://localhost:3100, /app/'],
], [24, 44, 32]));
add(gap());

// 부록 C
add(H1('부록 C. 수치 근거 파일'));
add(table(['절', '파일 (Halla-GeoData `Geo Data Analyst/data/` 기준)', '시각 / 커밋'], [
  ['2.1, 3.3', 'VALIDATION.json, jeju_grid_terrain_factors.csv, jeju_grid_forest.csv', '2026-10-17 격자 재생성; 임상도 9d95409'],
  ['3.1', 'outputs/jeju_weather/20261017/collection_summary.json, api_status.csv; runtime/kma/obs/aws_hourly/_backfill_progress.json', '2026-10-17; 백필 2026-10-19~'],
  ['4.2', 'obs_vs_forecast_check.json', '2026-10-16 00:30 발표'],
  ['4.3', 'verification_summary.json, physics_latest.json, uncertainty.json', '2026-10-17 08:30 ~ 10-18 22:30 (4회차)'],
  ['4.4', 'pressure_module_check.json', 'ASOS 2023-01 ~ 2026-10'],
  ['4.5, 7.2', 'https://jeju-tour-five.vercel.app/api/kma/{status,aws,now,warnings} 응답 저장본', '2026-10-30 22:26–22:31 KST'],
  ['5.1', 'foehn_cases_asos_summary.json, asos_case_catalogue_summary.json', 'ASOS 아카이브 33,218시간'],
  ['5.2', 'foehn_case_validation.json (gate_search 포함)', '횡단 바람 9,359시간'],
  ['6', 'residual_model_report.json (main e768cc0 → feat/forest-map 21bc915), training_set_era5_summary.json, ml_cells.json', '2026-10-18 23:00, 2026-10-19 11:37'],
  ['7.3', 'jeju-tour feat/flutter-app 29c82ab (app/README.md, pubspec.yaml)', '2026-10-29'],
], [12, 58, 30]));
add(gap());

// 참고문헌
add(H1('참고문헌'));
add(bullets([
  '이보라, 장근창, 김은숙, 강민석, 천정화, 임종환 (2019). 머신러닝 기법의 산림 총일차생산성 예측 모델 비교. 한국농림기상학회지, 21(1), 29–41. DOI 10.5532/KJAFM.2019.21.1.29.',
  'Mountain-Challenge-Project/Halla-GeoData (2026). 제주 소지역 국지기상 모델 설계 보고서 (2026-10-15); Geo Data Analyst README·산출 JSON. https://github.com/Mountain-Challenge-Project/Halla-GeoData',
  'jinminjoon/jeju-tour (2026). 한라산 완봉 제주 투어 플래너 "오름잇" — front, feat/flutter-app. https://github.com/jinminjoon/jeju-tour',
  'Stull, R. (2011). Wet-bulb temperature from relative humidity and air temperature. J. Appl. Meteor. Climatol., 50, 2267–2269. (여름 체감온도 습구 산식)',
  '기상청 API허브 (apihub.kma.go.kr): 지상관측 AWS 매분·ASOS, 동네예보 초단기, 수치모델 KIM, 레이더, 특보, 천리안 2A.',
  'Copernicus GLO-30 DEM; ESA WorldCover 2021; ETH Global Canopy Height 2020; Open-Meteo Historical Weather API (ERA5·ERA5-Land); 산림청 산림공간정보 임상도 1:5,000.',
]));

// ── document ─────────────────────────────────────────────────────────
const doc = new Document({
  creator: 'Halla-GeoData',
  title: '제주 소지역 국지기상 모델 구현·검증 보고서 (실데이터 기반)',
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 20 }, paragraph: { spacing: { line: 300 } } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 30, bold: true, color: '1F3864' }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 24, bold: true, color: '2E5C8A' }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 21, bold: true }, paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: {
    config: [
      { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 240 } } } }] },
      { reference: 'num', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 300 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1300, bottom: 1300, left: 1296, right: 1296 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: '제주 소지역 국지기상 모델 구현·검증 보고서 — ', size: 16, color: '777777' }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '777777' })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log('written', OUT, buf.length, 'bytes'); });
