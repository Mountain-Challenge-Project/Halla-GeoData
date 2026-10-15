"""Figures for Geo Data Analyst/docs/local_weather_model_report.md (run with a Python that has matplotlib, e.g. anaconda).

All plots are computed from files already in the repository: outputs/jeju_dashboard/data/grid.geojson
(cells with elevation, aspect), outputs/jeju_dashboard/data/forecast.json (KMA 초단기예보, 5 km points) and
Geo Data Analyst/docs/figures/transect_nw_se.csv (30 m DEM sampled along a NW-SE line through the summit). They show what the
physics modules of the design produce from one forecast issue; none of them is a validated prediction.
The committed figures and the report text correspond to the 2026-10-15 10:30 KST issue; re-running with a newer
forecast.json changes the numbers quoted in the report captions.
"""
import json, csv, math, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.collections import PolyCollection
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[2]
GDA = ROOT / 'Geo Data Analyst'
sys.path.insert(0, str(ROOT / 'work'))
from fetch_kma_forecast import dfs_xy  # noqa: E402

for f in ['malgun.ttf', 'malgunbd.ttf']:
    p = Path('C:/Windows/Fonts') / f
    if p.exists(): fm.fontManager.addfont(str(p))
plt.rcParams['font.family'] = 'Malgun Gothic'; plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150
OUT = GDA / 'docs/figures'; OUT.mkdir(parents=True, exist_ok=True)

grid = json.loads((ROOT / 'outputs/jeju_dashboard/data/grid.geojson').read_text('utf-8'))
fc = json.loads((ROOT / 'outputs/jeju_dashboard/data/forecast.json').read_text('utf-8'))
hours = fc['hours']; H0 = hours[0]
base = fc['base_time_kst'][:16].replace('T', ' ')

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def magnus_td(t, rh):
    a, b = 17.62, 243.12
    g = math.log(max(rh, 1) / 100.0) + a * t / (b + t)
    return b * g / (a - g)

cells = []
for f in grid['features']:
    p = f['properties']; ring = f['geometry']['coordinates'][0]
    lon = sum(q[0] for q in ring[:-1]) / (len(ring) - 1); lat = sum(q[1] for q in ring[:-1]) / (len(ring) - 1)
    x, y = dfs_xy(lon, lat); pt = fc['points'].get(f'{x},{y}')
    cells.append({'ring': [(q[0], q[1]) for q in ring], 'lon': lon, 'lat': lat, 'p': p, 'pt': pt})

def derive(c, h, vec_override=None, wsd_override=None):
    p, pt = c['p'], c['pt']
    if not pt: return None
    v = pt['hours'].get(h)
    if not v: return None
    t0, rh, wsd, vec = num(v['t1h']), num(v['reh']), num(v['wsd']), num(v.get('vec'))
    if vec_override is not None: vec = vec_override
    if wsd_override is not None: wsd = wsd_override
    if t0 is None or rh is None: return None
    t = t0 - 0.0065 * ((p.get('elev_mean') or 0) - (pt.get('elev_m') or 0))
    td0 = magnus_td(t0, rh)                       # point dew point (Magnus)
    td = td0 - 0.002 * ((p.get('elev_mean') or 0) - (pt.get('elev_m') or 0))  # dew-point lapse 2 degC/km (design)
    dep = t - td
    we = None
    if p.get('asp_r') is not None and p['asp_r'] >= 0.2 and vec is not None and wsd is not None:
        we = wsd * math.cos(math.radians(vec - p['asp_deg'])) * p['asp_r']
    vkm = (wsd or 0) * 3.6
    if t <= 10 and vkm >= 4.8:
        k = vkm ** 0.16; wc = 13.12 + 0.6215 * t - 11.37 * k + 0.3965 * t * k
    else: wc = t
    return {'t': t, 'td': td, 'dep': dep, 'we': we, 'wc': wc, 't0': t0, 'rh': rh, 'wsd': wsd, 'vec': vec, 'elev': p.get('elev_mean') or 0}

def cell_map(ax, values, cmap, vmin, vmax, title, label, highlight=None):
    polys = [c['ring'] for c in cells]; vals = np.array([np.nan if v is None else v for v in values], float)
    pc = PolyCollection(polys, array=vals, cmap=cmap, edgecolors='none')
    pc.set_clim(vmin, vmax); ax.add_collection(pc)
    if highlight is not None:
        hp = [c['ring'] for c, hbit in zip(cells, highlight) if hbit]
        if hp: ax.add_collection(PolyCollection(hp, facecolors='none', edgecolors='#d62728', linewidths=.6))
    ax.set_xlim(126.13, 126.98); ax.set_ylim(33.17, 33.58); ax.set_aspect(1 / math.cos(math.radians(33.4)))
    ax.set_title(title, fontsize=10); ax.set_xlabel('경도'); ax.set_ylabel('위도'); ax.tick_params(labelsize=7)
    cb = plt.colorbar(pc, ax=ax, shrink=.75, pad=.02); cb.set_label(label, fontsize=8); cb.ax.tick_params(labelsize=7)
    return pc

# ---------- Fig 1: model architecture ----------
fig, ax = plt.subplots(figsize=(9, 5.2)); ax.axis('off')
def box(x, y, w, h, text, fc='#eef3fb', ec='#3b5b8c'):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.02', fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha='center', va='center', fontsize=8.2, linespacing=1.4)
def arrow(x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>', mutation_scale=12, color='#444', lw=1))
box(0.02, 0.62, 0.27, 0.33, '격자 전역 입력 (유형 2)\n초단기예보·실황 5 km\nLDAPS 1.5 km (기압·850 hPa)\n레이더 500 m · GK2A 위성\nERA5 (과거 학습 기간)', '#eef3fb')
box(0.02, 0.22, 0.27, 0.33, '지형·지표 정적 인자\n고도·경사·경사향·집중도\nTPI·하늘개방도·해안거리\n16방위 상류 최고고도\n토지피복', '#f3f8ee', '#4e7d3a')
box(0.36, 0.52, 0.28, 0.4, '물리 모듈 (유형 3 인자)\n이슬점·VPD·LCL (Magnus)\n감률 고도 보정 (6.5 / 2 °C/km)\n푄 단면 계산·푄 지수\n풍상 노출·바람그늘·채널링\n지점기압 환산', '#fff6e5', '#b8741a')
box(0.36, 0.1, 0.28, 0.32, '기계학습 모듈\nRF · GBM · 소형 ANN\n(대조군: 선형 감률 보정)\n물리값 + 학습된 잔차\n분류(발생) → 회귀(강도)', '#fbeeee', '#a33')
box(0.71, 0.52, 0.27, 0.4, '산출 (셀 × 1시간)\n기온·이슬점·습도·기압\n체감온도·풍향풍속\n강수 확률·강도\n운무 가능·푄 조건 플래그\n신뢰 구간', '#eefbf3', '#2a7d4f')
box(0.71, 0.1, 0.27, 0.32, '정답·검증\nAWS·ASOS 지점 (고지대 AWS)\n고산 라디오존데\n연도 분리 + 지점 제외 교차검증\n사례 검증 (푄·호우·안개)', '#f0f0f0', '#555')
arrow(0.29, 0.78, 0.36, 0.74); arrow(0.29, 0.38, 0.36, 0.62); arrow(0.5, 0.52, 0.5, 0.42)
arrow(0.64, 0.72, 0.71, 0.72); arrow(0.64, 0.26, 0.71, 0.26); arrow(0.845, 0.52, 0.845, 0.42)
ax.text(0.5, 1.04, '그림 1. 소지역 국지기상 모델 구조 (논문의 입력 유형 1·2·3 구분을 따름)', ha='center', va='top', fontsize=10)
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
fig.savefig(OUT / 'fig1_architecture.png', bbox_inches='tight'); plt.close(fig)

# ---------- Fig 2: cell temperature map vs 5 km point value ----------
d0 = [derive(c, H0) for c in cells]
fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
cell_map(axs[0], [d['t0'] if d else None for d in d0], 'coolwarm', 8, 24, f'(a) 5 km 격자점 기온 T1H를 셀에 그대로 적용 ({H0[8:10]}시)', '°C')
cell_map(axs[1], [d['t'] if d else None for d in d0], 'coolwarm', 8, 24, '(b) 6.5 °C/km 감률로 셀 고도 보정한 추정 기온', '°C')
fig.suptitle(f'그림 2. 셀 추정 기온: 초단기예보 {base} KST 발표', fontsize=10)
fig.savefig(OUT / 'fig2_cell_temperature.png', bbox_inches='tight'); plt.close(fig)

# ---------- Fig 3: dew-point depression map and fog-possible cells ----------
fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
cell_map(axs[0], [d['td'] if d else None for d in d0], 'YlGnBu', -4, 16, f'(a) 셀 이슬점 추정 ({H0[8:10]}시, Magnus + 감률 2 °C/km)', '°C')
dep = [d['dep'] if d else None for d in d0]
cell_map(axs[1], dep, 'Blues_r', 0, 12, '(b) 기온-이슬점 차 (1 °C 이하 = 운무 가능, 빨간 테두리)', '°C', highlight=[v is not None and v <= 1 for v in dep])
fig.suptitle(f'그림 3. 이슬점 모듈 산출: 초단기예보 {base} KST', fontsize=10)
fig.savefig(OUT / 'fig3_dewpoint_depression.png', bbox_inches='tight'); plt.close(fig)

# ---------- Fig 4: lapse profiles (elevation vs T, Td) ----------
fig, ax = plt.subplots(figsize=(7.2, 4.6))
el = np.array([d['elev'] if d else np.nan for d in d0]); t = np.array([d['t'] if d else np.nan for d in d0]); td = np.array([d['td'] if d else np.nan for d in d0])
t0 = np.array([d['t0'] if d else np.nan for d in d0])
ax.scatter(t0, el, s=3, c='#bbb', label='5 km 격자점 기온 (셀 고도에 그대로)')
ax.scatter(t, el, s=3, c='#d62728', label='셀 추정 기온 (6.5 °C/km)')
ax.scatter(td, el, s=3, c='#1f77b4', label='셀 추정 이슬점 (2 °C/km)')
ax.set_xlabel('°C'); ax.set_ylabel('셀 평균 고도 (m)'); ax.grid(alpha=.3); ax.legend(fontsize=8, loc='upper right')
ax.set_title(f'그림 4. 고도에 따른 셀 기온·이슬점 추정 ({H0[8:10]}시, 7,518셀)', fontsize=10)
fig.savefig(OUT / 'fig4_lapse_profile.png', bbox_inches='tight'); plt.close(fig)

# ---------- Fig 5: foehn cross-section (NW -> summit -> SE) ----------
tr = list(csv.DictReader((OUT / 'transect_nw_se.csv').open(encoding='utf-8')))
dist = np.array([float(r['dist_km']) for r in tr]); z = np.array([float(r['elev_m']) if r['elev_m'] not in ('', 'nan') else np.nan for r in tr])
z = np.nan_to_num(z, nan=0.0); z = np.maximum(z, 0)
ridge_i = int(np.nanargmax(z)); ridge = z[ridge_i]
# windward point: forecast point of the first land cell on the NW side of the transect
nw = next(r for r in tr if float(r['elev_m'] or 0) > 5)
x, y = dfs_xy(float(nw['lon']), float(nw['lat'])); ptw = fc['points'].get(f'{x},{y}')
# use the hour with the strongest wind at that point for the illustration
hw = max(hours, key=lambda h: num(ptw['hours'][h]['wsd']) or 0)
v = ptw['hours'][hw]; T0, RH0, W0, V0 = num(v['t1h']), num(v['reh']), num(v['wsd']), num(v['vec'])
z0 = ptw['elev_m']; Td0 = magnus_td(T0, RH0); lcl = z0 + 125 * (T0 - Td0)
GD, GM = 9.8 / 1000, 6.0 / 1000
def parcel(zz, side):
    if side == 'up':  # windward ascent: dry to LCL, moist above
        if zz <= lcl: return T0 - GD * (zz - z0)
        return T0 - GD * (lcl - z0) - GM * (zz - lcl)
    # lee descent from the ridge: dry adiabatic all the way (moisture rained out above LCL)
    tr_ = T0 - GD * (max(lcl, z0) - z0) - GM * max(0, ridge - max(lcl, z0)) if ridge > lcl else T0 - GD * (ridge - z0)
    return tr_ + GD * (ridge - zz)
tp = np.array([parcel(zz, 'up') if i <= ridge_i else parcel(zz, 'lee') for i, zz in enumerate(z)])
tl = T0 - 0.0065 * (z - z0)   # simple lapse reference
fig, ax1 = plt.subplots(figsize=(9, 4.6)); ax2 = ax1.twinx()
ax1.fill_between(dist, 0, z, color='#c9b48a', alpha=.9, label='지형 (30 m DEM 단면)')
if ridge > lcl: ax1.axhline(lcl, color='#1f77b4', ls='--', lw=1, label=f'LCL 약  {lcl:,.0f} m (풍상측)')
ax1.set_ylabel('고도 (m)'); ax1.set_xlabel('북서 ← 거리 (km, 정상 기준) → 남동'); ax1.set_ylim(0, 2300)
ax2.plot(dist, tl, color='#999', lw=1.2, label='단순 감률 보정 기온 (6.5 °C/km)')
ax2.plot(dist, tp, color='#d62728', lw=1.8, label='공기덩이 기온: 건조·습윤 단열 상승 → 건조 단열 하강')
ax2.set_ylabel('기온 (°C)')
idx = ridge + 0
foehn_gain = tp[-1] - tl[-1]
ax1.set_title(f'그림 5. 푄 모듈 단면 (북서풍 가정): 풍상 격자점 {hw[8:10]}시 T {T0:.0f} °C, RH {RH0:.0f} %, 풍속 {W0:.1f} m/s, 실제 풍향 {V0:.0f}°\n'
              f'풍하측 해안의 푄 승온 = 공기덩이 기온 - 감률 보정 기온 = {foehn_gain:+.1f} °C (능선 {ridge:,.0f} m)', fontsize=9.5)
h1, l1 = ax1.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax1.legend(h1 + h2, l1 + l2, fontsize=7.5, loc='upper left')
fig.savefig(OUT / 'fig5_foehn_transect.png', bbox_inches='tight'); plt.close(fig)

# ---------- Fig 6: windward exposure, actual hour vs a NW 10 m/s scenario ----------
hmax = max(hours, key=lambda h: max((num(pt['hours'][h]['wsd']) or 0) for pt in fc['points'].values()))
da = [derive(c, hmax) for c in cells]; ds = [derive(c, hmax, vec_override=315.0, wsd_override=10.0) for c in cells]
fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
cell_map(axs[0], [d['we'] if d else None for d in da], 'RdBu_r', -6, 6, f'(a) 실제 예보 풍향·풍속 ({hmax[8:10]}시, 제주 최대 풍속 시각)', 'm/s (+ 풍상, - 풍하)')
cell_map(axs[1], [d['we'] if d else None for d in ds], 'RdBu_r', -6, 6, '(b) 시나리오: 북서풍 10 m/s 일괄 적용', 'm/s (+ 풍상, - 풍하)')
fig.suptitle('그림 6. 풍상 사면 노출 = 풍속 × cos(풍향 - 경사향) × 집중도 (집중도 < 0.2 셀은 공백)', fontsize=10)
fig.savefig(OUT / 'fig6_wind_exposure.png', bbox_inches='tight'); plt.close(fig)

# ---------- Fig 7: summit point 6-hour series ----------
sp = fc['points']['54,36']
T = [num(sp['hours'][h]['t1h']) for h in hours]; RH = [num(sp['hours'][h]['reh']) for h in hours]
W = [num(sp['hours'][h]['wsd']) for h in hours]; V = [num(sp['hours'][h]['vec']) for h in hours]
TD = [magnus_td(a, b) for a, b in zip(T, RH)]
summit_cell = max(cells, key=lambda c: c['p'].get('elev_max') or 0)
TC = [derive(summit_cell, h)['t'] for h in hours]; WC = [derive(summit_cell, h)['wc'] for h in hours]
xs = [h[8:10] + '시' for h in hours]
fig, axs = plt.subplots(1, 3, figsize=(12, 3.6))
axs[0].plot(xs, T, 'o-', c='#d62728', label=f'격자점 기온 (고도 {sp["elev_m"]:,.0f} m)'); axs[0].plot(xs, TD, 's-', c='#1f77b4', label='격자점 이슬점 (Magnus)')
axs[0].plot(xs, TC, '^-', c='#ff7f0e', label=f'정상 셀 추정 기온 ({summit_cell["p"]["elev_mean"]:,.0f} m)'); axs[0].plot(xs, WC, 'v--', c='#9467bd', label='정상 셀 체감온도')
axs[0].set_ylabel('°C'); axs[0].legend(fontsize=7); axs[0].grid(alpha=.3); axs[0].set_title('(a) 기온·이슬점·체감온도', fontsize=9)
axs[1].bar(xs, RH, color='#7fb8e2'); axs[1].set_ylim(0, 100); axs[1].set_ylabel('%'); axs[1].set_title('(b) 상대습도', fontsize=9); axs[1].grid(alpha=.3, axis='y')
axs[2].bar(xs, W, color='#bbb', label='풍속 m/s'); ax2 = axs[2].twinx(); ax2.plot(xs, V, 'o-', c='#2a7d4f', label='풍향 °'); ax2.set_ylim(0, 360)
axs[2].set_ylabel('m/s'); ax2.set_ylabel('풍향 (°)'); axs[2].set_title('(c) 풍속·풍향', fontsize=9)
fig.suptitle(f'그림 7. 한라산 정상 5 km 격자점 (54,36) 초단기예보 6시간: {base} KST 발표', fontsize=10)
fig.tight_layout(); fig.savefig(OUT / 'fig7_summit_series.png', bbox_inches='tight'); plt.close(fig)

# ---------- Fig 8: validation design schematic ----------
fig, axs = plt.subplots(1, 2, figsize=(11, 3.4))
ax = axs[0]; ax.axis('off'); ax.set_title('(a) 연도 분리 검증', fontsize=9.5)
for i, (yr, kind) in enumerate([('2023', '학습'), ('2024', '학습'), ('2025', '학습'), ('2026', '검증')]):
    ax.add_patch(FancyBboxPatch((i * 0.24 + 0.02, 0.35), 0.21, 0.3, boxstyle='round,pad=0.01', fc='#eef3fb' if kind == '학습' else '#fbeeee', ec='#555'))
    ax.text(i * 0.24 + 0.125, 0.5, f'{yr}\n{kind}', ha='center', va='center', fontsize=9)
ax.text(0.5, 0.12, '논문의 2006–2013 학습 / 2014–2015 검증 구성과 같음', ha='center', fontsize=8); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
ax = axs[1]; ax.axis('off'); ax.set_title('(b) 지점 제외 교차검증 (leave-one-station-out)', fontsize=9.5)
names = ['제주', '고산', '성산', '서귀포', '윗세오름', '진달래밭', '어리목', '…']
for i, n in enumerate(names):
    held = (i == 4)
    ax.add_patch(FancyBboxPatch((i * 0.12 + 0.02, 0.4), 0.1, 0.28, boxstyle='round,pad=0.01', fc='#fbeeee' if held else '#eef3fb', ec='#555'))
    ax.text(i * 0.12 + 0.07, 0.54, n, ha='center', va='center', fontsize=7.5)
ax.text(0.5, 0.15, '한 지점을 빼고 학습해 그 지점을 예측 → 관측이 없는 셀의 오차 추정치. 모든 지점에 대해 반복', ha='center', fontsize=8)
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
fig.suptitle('그림 8. 검증 설계', fontsize=10)
fig.savefig(OUT / 'fig8_validation_design.png', bbox_inches='tight'); plt.close(fig)

# numbers for the report
fogn = sum(1 for v in dep if v is not None and v <= 1); wn = sum(1 for d in ds if d and d['we'] is not None and d['we'] >= 4)
print(json.dumps({'base': base, 'hour0': H0, 'hour_maxwind': hmax, 'windward_point': f'{x},{y}', 'windward_hour': hw, 'T0': T0, 'RH0': RH0, 'W0': W0, 'V0': V0,
                  'Td0': round(Td0, 1), 'lcl_m': round(lcl), 'ridge_m': round(ridge), 'foehn_gain_C': round(float(foehn_gain), 1),
                  'fog_cells_h0': fogn, 'scenario_windward_cells_ge4': wn, 'cells': len(cells),
                  't_range_cells': [round(float(np.nanmin(t)), 1), round(float(np.nanmax(t)), 1)], 'summit_elev_m': sp['elev_m']}, ensure_ascii=False))
