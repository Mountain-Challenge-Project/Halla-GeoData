"""실데이터 보고서(docs/제주_소지역_국지기상_모델_실데이터_보고서.docx) 그림 7장 생성.

입력: data/*.json (검증·사례·기압), docs/figures/report_20261030/data/ (학습 보고서 스냅샷 2건, 2026-10-30 운영 API 응답 3건).
실행: anaconda Python (matplotlib) — python "Geo Data Analyst/scripts/make_report_figures.py"
"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.size'] = 10
HERE = Path(__file__).parent
GDA = Path(__file__).resolve().parents[1] / 'data'
RPT = Path(__file__).resolve().parents[1] / 'docs' / 'figures' / 'report_20261030'
OUT = RPT
OUT.mkdir(exist_ok=True)
C = {'phys': '#8a8f98', 'ridge': '#b9bec7', 'rf': '#4e79a7', 'gbm': '#2a4d7a', 'raw': '#c9ced6', 'lapse': '#4e79a7', 'foehn': '#e15759', 'persist': '#c9ced6'}

def save(fig, name):
    fig.savefig(OUT / name, dpi=160, bbox_inches='tight')
    plt.close(fig)
    print('saved', name)

# ── A. residual model results (first model 10-18 vs retrain 10-19) ──
# 두 학습 회차의 보고서 스냅샷 (main 2026-10-18, feat/forest-map 2026-10-19)
first = json.load(open(RPT / 'data' / 'residual_model_report_20261018.json', encoding='utf-8'))
retr = json.load(open(RPT / 'data' / 'residual_model_report_20261019.json', encoding='utf-8'))
fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
for ax, tgt, title in zip(axes, ['t', 'td'], ['기온 (°C)', '이슬점 (°C)']):
    labels = ['물리만', '릿지', 'RF', 'GBM']
    x = np.arange(4); w = 0.38
    for off, rep, name, alpha in [(-w/2, first, '첫 모델 (10-18, 133,871행)', 0.55), (w/2, retr, '재학습 (10-19, 144,572행)', 1.0)]:
        v = rep['targets'][tgt]
        vals = [v['physics_only']['rmse'], v['loso']['ridge']['rmse'], v['loso']['rf']['rmse'], v['loso']['gbm']['rmse']]
        cols = [C['phys'], C['ridge'], C['rf'], C['gbm']]
        bars = ax.bar(x + off, vals, w, color=cols, alpha=alpha, label=name, edgecolor='white')
        for b, val in zip(bars, vals):
            ax.text(b.get_x() + b.get_width()/2, val + 0.04, f'{val:.2f}', ha='center', va='bottom', fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_title(f'{title} — 지점 제외 교차검증 RMSE', fontsize=10)
    ax.set_ylim(0, max(5.6, 1) if tgt == 'td' else 2.3); ax.grid(axis='y', alpha=0.3)
    ax.spines[['top', 'right']].set_visible(False)
h, l = axes[0].get_legend_handles_labels()
fig.legend(h[:1] + h[1:2], ['연한 색: 첫 모델 (2026-10-18, 133,871행)', '진한 색: 재학습 (2026-10-19, 144,572행, 임상도 인자·산지 백필 반영)'], loc='lower center', ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.1), fontsize=9)
save(fig, 'figA_model_results.png')

# ── B. station verification by elevation band ──
ver = json.load(open(GDA / 'verification_summary.json', encoding='utf-8'))
bands = ['<300 m', '300-1000 m', '>=1000 m']
fig, axes = plt.subplots(1, 2, figsize=(9, 3.2))
x = np.arange(3); w = 0.26
ax = axes[0]
for i, (key, lab, col) in enumerate([('raw_5km_point', '5 km 원값 (무보정)', C['raw']), ('lapse_corrected', '감률 보정', C['lapse']), ('foehn_aware', '푄 반영', C['foehn'])]):
    vals = [ver['by_elevation'][b]['temperature'][key]['rmse'] for b in bands]
    bars = ax.bar(x + (i-1)*w, vals, w, color=col, label=lab)
    for b_, v_ in zip(bars, vals): ax.text(b_.get_x()+w/2, v_+0.05, f'{v_:.2f}', ha='center', fontsize=8)
ax.set_xticks(x); ax.set_xticklabels([f"{b}\n(n={ver['by_elevation'][b]['temperature']['raw_5km_point']['n']})" for b in bands])
ax.set_title('기온 RMSE (°C) — 고도대별', fontsize=10); ax.legend(frameon=False, fontsize=8); ax.grid(axis='y', alpha=0.3); ax.spines[['top','right']].set_visible(False)
ax = axes[1]
for i, (key, lab, col) in enumerate([('lapse_corrected', '감률 보정', C['lapse']), ('foehn_aware', '푄 반영', C['foehn'])]):
    vals = [ver['by_elevation'][b]['dew_point'][key]['rmse'] for b in bands]
    bias = [ver['by_elevation'][b]['dew_point'][key]['bias'] for b in bands]
    bars = ax.bar(x + (i-0.5)*w, vals, w, color=col, label=lab)
    for b_, v_, bi in zip(bars, vals, bias): ax.text(b_.get_x()+w/2, v_+0.12, f'{v_:.1f}', ha='center', fontsize=8)
ax.set_xticks(x); ax.set_xticklabels(bands); ax.set_ylim(0, 10)
ax.set_title('이슬점 RMSE (°C) — 고도대별', fontsize=10); ax.legend(frameon=False, fontsize=8); ax.grid(axis='y', alpha=0.3); ax.spines[['top','right']].set_visible(False)
fig.suptitle(f"3단계 지점 검증 누적: {ver['issues']}회차 × 지점 = {ver['station_rows']}행 (2026-10-17 08:30 ~ 10-18 22:30 발표)", fontsize=10, y=1.02)
save(fig, 'figB_verification_elev.png')

# ── C. foehn case validation ──
fv = json.load(open(GDA / 'foehn_case_validation.json', encoding='utf-8'))
fig, axes = plt.subplots(1, 3, figsize=(11, 3.2), gridspec_kw={'width_ratios': [1, 1, 1.3]})
for ax, var, title, unit in [(axes[0], 'temperature', '풍하 지점 기온 RMSE', '°C'), (axes[1], 'humidity', '풍하 지점 습도 RMSE', '%p')]:
    x = np.arange(2); w = 0.26
    for i, (key, lab, col) in enumerate([('persist', '풍상 값 지속', C['persist']), ('lapse', '감률 보정', C['lapse']), ('foehn', '공기덩이(푄) 계산', C['foehn'])]):
        vals = [fv['results']['event'][var][key]['rmse'], fv['results']['other'][var][key]['rmse']]
        bars = ax.bar(x + (i-1)*w, vals, w, color=col, label=lab)
        for b_, v_ in zip(bars, vals): ax.text(b_.get_x()+w/2, v_+0.3, f'{v_:.1f}', ha='center', fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels([f"푄 사례\n{fv['hours']['event']}시간", f"그 밖 횡단 바람\n{fv['hours']['other']:,}시간"], fontsize=9)
    ax.set_title(f'{title} ({unit})', fontsize=10); ax.grid(axis='y', alpha=0.3); ax.spines[['top','right']].set_visible(False)
axes[0].set_ylim(0, 7.6); axes[1].set_ylim(0, 44)
axes[0].legend(frameon=False, fontsize=8, loc='upper left')
ax = axes[2]
hh = fv['gate_search']['event_hours_by_hour_of_day']
ax.bar([int(k) for k in hh], list(hh.values()), color=C['foehn'])
ax.axvspan(10.5, 16.5, color=C['foehn'], alpha=0.12)
ax.set_title('푄 사례 시간의 시각 분포 (KST)', fontsize=10); ax.set_xlabel('시'); ax.set_ylabel('시간 수'); ax.set_xticks(range(0, 24, 3)); ax.spines[['top','right']].set_visible(False)
ax.text(13.5, max(hh.values())*0.95, '적용 창 11–16시\n(30 % 블렌드)', ha='center', va='top', fontsize=8)
fig.suptitle(f"5단계 푄 사례 검증 — ASOS 횡단 바람(풍상 {fv['wind_min_ms']:.0f} m/s 이상) 2023-01~2026-10, 능선 약 {fv['ridges_m']['E-W']:,.0f} m", fontsize=10, y=1.03)
save(fig, 'figC_foehn_validation.png')

# ── D. case catalogues by month ──
fe = json.load(open(GDA / 'foehn_cases_asos_summary.json', encoding='utf-8'))
cc = json.load(open(GDA / 'asos_case_catalogue_summary.json', encoding='utf-8'))
months = [f'{m:02d}' for m in range(1, 13)]
fig, axes = plt.subplots(1, 3, figsize=(11, 2.9))
for ax, d, title, col in [(axes[0], fe['events_by_month'], f"푄 후보 사례 {fe['events']}건 (월별)", C['foehn']), (axes[1], cc['fog_by_month'], f"안개 관측 {cc['fog_hours']:,}시간 (월별)", '#59a14f'), (axes[2], cc['heavy_rain_by_month'], f"호우 {cc['heavy_rain_hours']}시간 (1시간 20 mm 또는 3시간 60 mm 이상)", C['lapse'])]:
    ax.bar(range(1, 13), [d.get(m, 0) for m in months], color=col)
    ax.set_xticks(range(1, 13)); ax.set_title(title, fontsize=10); ax.spines[['top','right']].set_visible(False); ax.grid(axis='y', alpha=0.3)
fig.suptitle('ASOS 4지점(제주·고산·성산·서귀포) 아카이브 2023-01 ~ 2026-10에서 선별한 사례 라벨', fontsize=10, y=1.04)
save(fig, 'figD_case_catalogue.png')

# ── E. live AWS snapshot (production API, 2026-10-30) ──
aws = json.load(open(RPT / 'data' / 'aws_live.json', encoding='utf-8'))['data']
st = [s for s in aws['stations'] if s['obs'] and s['obs']['ta'] is not None]
tm = aws['tm']; tms = f'{tm[:4]}-{tm[4:6]}-{tm[6:8]} {tm[8:10]}:{tm[10:12]} KST'
mtn = {871, 965, 867, 870, 868, 869, 753, 782}
fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
ax = axes[0]
ref = next(s for s in st if s['stn'] == 184)
zz = np.linspace(0, 1950, 50)
ax.plot(ref['obs']['ta'] - 0.0065 * (zz - ref['elev']), zz, color=C['lapse'], lw=1.2, label=f"제주 ASOS 기준 6.5 °C/km 감률선")
for s in st:
    o = s['obs']; m = s['stn'] in mtn
    ax.scatter(o['ta'], s['elev'], s=36 if m else 18, color=C['foehn'] if m else '#555', zorder=3)
    if m or s['stn'] in (184, 188):
        ax.annotate(s['name'], (o['ta'], s['elev']), xytext=(4, 2), textcoords='offset points', fontsize=7.5)
ax.set_xlabel('기온 (°C)'); ax.set_ylabel('관측소 고도 (m)'); ax.set_title(f'AWS {len(st)}지점 기온 — {tms}', fontsize=10)
ax.legend(frameon=False, fontsize=8, loc='upper right'); ax.grid(alpha=0.3); ax.spines[['top','right']].set_visible(False)
ax = axes[1]
for s in st:
    o = s['obs']; m = s['stn'] in mtn
    if o['hm'] is None: continue
    ax.scatter(o['hm'], s['elev'], s=36 if m else 18, color=C['foehn'] if m else '#555', zorder=3)
    if m: ax.annotate(s['name'], (o['hm'], s['elev']), xytext=(4, 2), textcoords='offset points', fontsize=7.5)
ax.set_xlabel('상대습도 (%)'); ax.set_title('AWS 상대습도 — 같은 시각 (붉은색: 한라산 8지점)', fontsize=10); ax.grid(alpha=0.3); ax.spines[['top','right']].set_visible(False)
save(fig, 'figE_live_profile.png')

# ── F. RF importance (retrain) ──
fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4))
NAMES = {'hour_kst': '시각(KST)', 'doy_cos': '계절 cos', 'doy_sin': '계절 sin', 'lcl_rel_m': 'LCL 상대 고도', 'lapse_td': '감률 이슬점', 't1h': '예보 기온', 'lapse_t': '감률 기온', 'reh': '예보 습도', 'pt_elev_m': '격자점 고도', 'cell_elev_m': '셀 고도', 'stn_ht_m': '지점 고도', 'coast_km': '해안 거리', 'asp_cos': '경사향 cos', 'asp_sin': '경사향 sin', 'lc_crop': '경작지 비율', 'canopy_mean_m': '수관고', 'lc_builtup': '시가지 비율', 'lc_tree': '수목 비율', 'asp_r': '경사향 집중도'}
for ax, tgt, title in zip(axes, ['t', 'td'], ['기온 잔차', '이슬점 잔차']):
    imp = retr['targets'][tgt]['importance_rf'][:12][::-1]
    ax.barh([NAMES.get(k, k) for k, _ in imp], [v for _, v in imp], color=C['rf'])
    for i, (_, v) in enumerate(imp): ax.text(v + 0.002, i, f'{v:.3f}', va='center', fontsize=7.5)
    ax.set_title(f'{title} — 랜덤포레스트 변수 중요도 상위 12 (재학습)', fontsize=10); ax.spines[['top','right']].set_visible(False); ax.set_xlim(0, max(v for _, v in imp) * 1.25)
save(fig, 'figF_importance.png')

# ── G. system pipeline diagram ──
fig, ax = plt.subplots(figsize=(10, 4.6)); ax.set_xlim(0, 100); ax.set_ylim(0, 46); ax.axis('off')
def box(x, y, w, h, title, lines, fc='#eef3fa', ec='#4e79a7'):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.4', fc=fc, ec=ec, lw=1.2))
    ax.text(x + w/2, y + h - 1.6, title, ha='center', va='top', fontsize=9.5, fontweight='bold')
    ax.text(x + 1.2, y + h - 4.6, '\n'.join(lines), ha='left', va='top', fontsize=7.3, linespacing=1.35)
def arrow(x1, y1, x2, y2, text='', col='#555'):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>', mutation_scale=12, color=col, lw=1.1))
    if text: ax.text((x1+x2)/2, (y1+y2)/2 + 0.9, text, ha='center', fontsize=7.5, color=col)
ax.text(1, 45, 'Halla-GeoData (Mountain-Challenge-Project)', fontsize=10, fontweight='bold', color='#2a4d7a')
box(1, 26, 22, 17, '격자 전역 입력', ['API허브 초단기예보·실황 5 km', '레이더 PCPH 500 m · KIM 850/925', 'AWS 매분 42지점 · ASOS 4 · 특보', '지형 GLO-30 → 9,449셀 인자', '외부: ERA5(Open-Meteo) · 임상도'])
box(25, 26, 22, 17, '물리 모듈', ['physics_modules.py · 대시보드 JS', 'Magnus 이슬점 · LCL · VPD', '감률 6.5 / 2 °C/km 보정', '푄 단면 (습윤단열 적분)', '지점기압 · 체감온도 · 풍상 노출'])
box(49, 26, 22, 17, '잔차 학습', ['train / apply_residual_model.py', '특징 47개 · 릿지 · RF · GBM', '지점 제외 교차검증 · 시간 분리', '144,572행 학습 (2026-10-19)', '전 셀 적용 → ml_cells.json'])
box(73, 26, 26, 17, '라이브 대시보드', ['Leaflet · 공유 DB (radar/latest, ml)', '색상 기준 20개 · 강조 레이어', '푄 조건 · 운무 가능 · 내 위치 강수', '셀 상세: ±RMSE · 보정량 · 상류 점', '검증 누적 verify_stations.py'])
arrow(23.5, 34.5, 24.5, 34.5); arrow(47.5, 34.5, 48.5, 34.5); arrow(71.5, 34.5, 72.5, 34.5)
ax.text(1, 22.3, 'jeju-tour (jinminjoon) — 오름잇 서비스', fontsize=10, fontweight='bold', color='#2a4d7a')
box(1, 3, 31, 17, 'Express 서버 (src/kma.ts)', ['/api/kma/status · now · aws · warnings', '키는 서버에만 (KMA_API_KEY, Vercel 환경변수)', '캐시: 실황 5분 · 예보 10분 · AWS 3분 · 특보 10분', 'DFS 5 km 격자 변환 · 물리 모듈 이식', '(감률 · 이슬점 · LCL · 체감온도 · 운무 판정)'], fc='#f3f6ee', ec='#59a14f')
box(35, 3, 30, 17, 'React 웹 (prototype/client)', ['WeatherLivePage.tsx · WeatherMap.tsx', 'Google Maps hybrid 위성 + AWS 핀', '내 위치(GPS · 지도 클릭 · 프리셋) 실황·예보', '한라산 8지점 묶음 · 특보 배지', 'Vercel: jeju-tour-five.vercel.app'], fc='#f3f6ee', ec='#59a14f')
box(68, 3, 31, 17, 'Flutter 앱 (app/)', ['Dart 46파일 7,354줄: 웹 · Android · iOS', 'weather_live_page.dart · weather_map.dart', 'google_maps_flutter · geolocator', '같은 /api 봉투 {success, data}', '웹 빌드는 Express /app 아래 같은 출처'], fc='#f3f6ee', ec='#59a14f')
arrow(32.5, 11.5, 34.5, 11.5); arrow(65.5, 11.5, 67.5, 11.5)
arrow(36, 25.6, 24, 20.6, '', '#8a3a3a'); ax.text(37.5, 24.2, '물리 산식 이식 (TypeScript)', fontsize=7.5, color='#8a3a3a')
save(fig, 'figG_pipeline.png')

now = json.load(open(RPT / 'data' / 'now_jeju.json', encoding='utf-8'))['data']
print('jeju now', now['point'], now['ncst'], now['derived'])
