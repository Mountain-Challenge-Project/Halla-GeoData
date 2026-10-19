# Geo Data Analyst — 제주 소지역 국지기상 예측 모델

이 폴더는 Halla-GeoData 저장소 안에서 **기상 예측 모델**에 해당하는 부분만 모은 것입니다. 이슬점 온도와 푄(foehn) 현상을 중심으로, 500 m 격자 셀 단위의 국지 기상(기온·이슬점·습도·기압·체감온도·풍향풍속·강수·운무)을 추정하는 모델의 설계서, 자료 수집 스크립트, 산출 자료가 들어 있습니다. 지형 경사 분석, 레이더 변환, 대시보드 자체는 저장소 본체(`work/`, `outputs/`)에 있고, 이 폴더의 산출물을 읽기만 합니다.

참조 방법론: 이보라 외(2019), 머신러닝 기법의 산림 총일차생산성 예측 모델 비교, 한국농림기상학회지 21(1). 점 관측을 정답으로 두고 격자 전역 입력과 물리 유도 인자로 기계학습 모델을 학습해 공간으로 확장하는 구조를 따릅니다.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `docs/local_weather_model_report.md` | 설계 보고서 전문 (요약, 논문 검토, 모델 구조, 물리 모듈, 기계학습·검증 설계, 수집 데이터, 활용 방안, 일정, 산식). Word 판은 `docs/제주_소지역_국지기상_모델_설계_보고서.docx` |
| `docs/local_weather_model_design.md` | 설계안 요약판 (수집 데이터 표 3개, 활용 방안) |
| `docs/figures/` | 보고서 그림 8장과 한라산 북서–남동 DEM 단면 표본 (`transect_nw_se.csv`) |
| `scripts/fetch_kma_stations.py` | 기상청 API허브 지점정보(AWS·ASOS) → 제주 지점 목록, 500 m 셀 매핑 |
| `scripts/fetch_kma_obs.py` | AWS 1분·ASOS 정시 관측 수집기 (정답 자료), ASOS 과거 소급 수집 |
| `scripts/build_terrain_factors.py` | 30 m DSM에서 셀별 지형 파생 인자 계산 (QGIS Python) |
| `scripts/verify_obs_vs_forecast.py` | 감률 보정 기온·이슬점을 같은 시각 AWS 관측과 비교 |
| `scripts/make_design_figures.py` | 보고서 그림 생성 (matplotlib) |
| `scripts/fetch_kim_levels.py` | KIM 국지모델(1.5 km) 925·850 hPa 기온·습도·바람을 5 km 격자점으로 집계 (푄 모듈 상류 공기·횡단 바람) |
| `scripts/physics_modules.py` | 2단계 물리 모듈 참조 구현: Magnus 이슬점, LCL, 습윤단열감률, 셀 기온·이슬점, 푄 단면 계산 |
| `scripts/compute_stage2.py` | 현재 예보에 물리 모듈을 전 셀에 적용하고 AWS 지점과 비교 → `data/physics_latest.json` |
| `scripts/verify_stations.py` | 3단계 지점 검증 누적: 매 실행의 지점별 원값·감률·푄 반영 추정과 관측을 로컬 아카이브에 쌓고 고도대·시각·푄 조건별 통계 → `data/verification_summary.json` |
| `scripts/verify_pressure_asos.py` | 지점기압 모듈(정역학)을 ASOS 3년·AWS 고지대 관측으로 검증 → `data/pressure_module_check.json` |
| `scripts/find_foehn_cases_asos.py` | ASOS 동서·남북 지점 쌍으로 푄 후보 사례 선별 → `data/foehn_cases_asos.csv`, 요약 JSON (5단계 사례 라벨) |
| `scripts/RUN_PIPELINE.cmd` | 관측 → 예보 → (6시간마다 KIM) → 물리 모듈 → 지점 검증 누적 → 특징 아카이브를 한 번에 실행 (작업 스케줄러 매시 등록용) |
| `scripts/archive_features.py` | 4단계 학습용 특징 아카이브: 지점별 시간·지형·예보·KIM·물리값·관측 목표를 한 행으로 누적 (`runtime/kma/verification/features.csv`) |
| `scripts/train_residual_model.py` | 4단계 잔차 학습 (anaconda Python): 릿지 대조군·랜덤포레스트·그래디언트 부스팅, 지점 제외 교차검증·시간 분리 검증, 변수 중요도 → `data/residual_model_report.json`, 모델은 로컬 `runtime/kma/models/` |
| `scripts/apply_residual_model.py` | 학습된 잔차 모델을 전 셀에 적용 → `outputs/jeju_dashboard/data/ml_cells.json` (모델이 없으면 `no_model`) |
| `scripts/RUN_TRAIN.cmd` | 주 1회: 재분석 짝 학습 자료 재구성 → 재학습(`--with-era5`) → 셀 적용 배치 |
| `scripts/import_aws_history_csv.py` | 수집기 CSV(`outputs/jeju_weather/*/csv/aws_hourly_snapshot_*.csv`) 또는 포털 CSV 변환본을 시간 아카이브 `runtime/kma/obs/aws_hourly/`로 들여옴 |
| `scripts/backfill_aws_hourly.py` | **AWS 과거 시간자료 소급 수집(1순위 KMA 관측)**: API허브 매분 아카이브를 하루 단위(tm1/tm2)로 받아 정각 값만 시간 아카이브에 저장, 지점별 진행 상태 저장·재개, 지점 동시 요청 |
| `scripts/foehn_case_validation.py` | 5단계 푄 사례 검증: ASOS 횡단 바람 9,359시간에 공기덩이 모듈을 적용해 풍하 지점 관측과 비교, 적용 규칙(게이트·블렌드) 탐색 → `data/foehn_case_validation.json` |
| `scripts/asos_case_catalogue.py` | 안개·호우 사례 목록(ASOS)과 운무 규칙 적중률 → `data/fog_cases_asos.csv`, `data/heavy_rain_cases_asos.csv`, 요약 JSON |
| `scripts/fetch_era5_openmeteo.py` | **차선 자료**: Open-Meteo 아카이브 API로 42지점의 ERA5-Land 지상·ERA5 925/850 hPa 시간자료(2023~)를 연도별 CSV로 받음 (계정 불필요). 1순위는 Copernicus CDS 원자료이며, `runtime/kma/era5_cds/`에 CDS NetCDF가 있으면 학습 자료 구성 시 그쪽을 우선 사용 |
| `scripts/build_landcover_factors.py` | **차선 자료**: ESA WorldCover·ETH 수관고 타일에서 셀별 토지피복 비율·수관고 계산 (QGIS Python, scripts 폴더에서 실행) → `data/jeju_grid_landcover.csv`. 1순위는 환경부 세분류 토지피복도·산림청 임상도이며, 받으면 같은 열 이름으로 재계산해 덮어씀 |
| `scripts/RUN_OBS.cmd` | 관측 수집 주기 실행용 배치 (작업 스케줄러 등록 예시 포함) |
| `data/kma_stations_jeju.csv`, `.geojson` | 제주 지점 42개(ASOS 4): 좌표, 노장고도, DSM 고도, 속한 셀(부속섬 포함), 셀 고도·경사 |
| `data/jeju_grid_terrain_factors.csv` | 셀 9,449개(해안 완충 포함)의 TPI·하늘개방도·해안 거리·16방위 상류 최고고도/거리 |
| `data/obs_vs_forecast_check.json` | 첫 물리 점검 결과 (지점별 관측·추정값, 통계) |
| `data/physics_latest.json` | 2단계 물리 모듈 점검 결과 (셀 집계: 구름 속·운무·푄 지수·푄 조건, 지점별 감률/푄 반영 기온·이슬점 대 관측) |
| `data/verification_summary.json` | 3단계 누적 검증 통계 (원값 대조군·감률·푄 반영, 고도대·시각·푄 조건별) |
| `data/pressure_module_check.json` | 지점기압 모듈 검증: ASOS 4지점 3년 RMSE 0.17 hPa, 고지대 AWS 0.2–0.3 hPa |
| `data/foehn_cases_asos.csv` | ASOS 아카이브(2023-01~)에서 선별한 푄 후보 사례 145건 (봄철 집중, 풍하 성산 104건) |
| `data/era5_openmeteo_manifest.json` | ERA5 다운로드 목록(지점·모델·연도·행수·SHA-256); 자료는 로컬 |
| `data/external_rasters_manifest.json` | WorldCover·수관고 타일 출처·SHA-256; 자료는 로컬 |
| `data/jeju_grid_landcover.csv` | 셀 9,449개의 토지피복 비율(%)과 수관고(m); `grid.geojson`에 결합 |

관측 원자료는 `runtime/kma/obs/`(저장소 루트, Git 제외)에 월별 CSV로 쌓이고, 지점별 최신값만 대시보드용 `outputs/jeju_dashboard/data/obs_latest.json`과 공유 DB 문서 `radar/obs`에 씁니다.

## 모델 구조 요약

1. **격자 전역 입력**: 초단기예보·실황(5 km), KIM 국지모델 등압면(850·925 hPa), 레이더 강수·반사도(500 m), 천리안 2A 산출물, 지형 인자.
2. **물리 모듈**: Magnus 이슬점·VPD·상승응결고도(LCL), 기온감률 6.5 °C/km·이슬점 감률 2 °C/km 고도 보정, 한라산 횡단 단열 계산에 의한 푄 지수, 풍상 사면 노출·바람그늘 깊이, 정역학 지점기압, 체감온도.
3. **기계학습 모듈**: 물리값과 AWS 관측의 잔차를 랜덤포레스트·부스팅·소형 ANN으로 학습. 대조군은 선형 감률 보정값.
4. **검증**: 연도 분리, 지점 제외 교차검증(leave-one-station-out), 푄·호우·안개 사례 검증. 지표 R·RMSE·MSE·편향.
5. **산출**: 셀 × 1시간 기온·이슬점·습도·기압·체감온도·풍향풍속·강수·운무 가능·푄 조건 플래그·신뢰 구간 → 대시보드 색상 기준·강조 레이어.

자세한 산식은 보고서 부록 A에 있습니다.

## 자료 현황 (2026-10-16 기준)

| 구분 | 자료 | 상태 |
|---|---|---|
| 정답 | AWS 1분(제주 42지점), ASOS 시간(4지점), 지점정보, 제주 라디오존데(47186) | API 승인, 수집 중. ASOS는 2023-01부터 소급 수집 완료(로컬). AWS 과거 시간자료는 `backfill_aws_hourly.py`로 소급 중(산지 8지점 2025-10~ 우선, 이어서 전 지점·전 기간) |
| 격자 입력 | 초단기예보·실황, 단기예보, 레이더 PCPH·HSR, AWS 객관분석 격자, KIM 등압면, 천리안 2A L2, 특보 | API 승인 |
| 격자 입력 | KIM 지상 2D, 낙뢰 | 활용신청 대기 |
| 지형 | 셀 고도·경사·경사향·집중도, TPI, 하늘개방도, 해안 거리, 16방위 상류 최고고도 | 완료 (`grid.geojson`에 결합) |
| 외부 (1순위, 계정 필요) | AWS 과거 분자료(기상자료개방포털 CSV), Copernicus CDS ERA5, 환경부 토지피복도, 산림청 임상도, MODIS, Sentinel-3 | 미수집 (보고서 5장에 경로) |
| 외부 (차선, 계정 불필요) | Open-Meteo ERA5-Land·ERA5(2023~, 42지점), ESA WorldCover 2021, ETH 수관고 2020 | 수집됨 (로컬). 1순위 자료가 들어오면 교체 |

## 실행 순서

저장소 루트에서 실행합니다. 네트워크 스크립트는 시스템 Python(`.env`의 `KMA_API_KEY` 필요), 지형 스크립트는 QGIS Python, 그림은 matplotlib이 있는 Python을 씁니다.

```bash
python "Geo Data Analyst/scripts/fetch_kma_stations.py"
```

```bash
python "Geo Data Analyst/scripts/fetch_kma_obs.py"
```

```bash
python "Geo Data Analyst/scripts/fetch_kma_obs.py" --asos-backfill 2023-01-01
```

```bash
cd "Geo Data Analyst/scripts" && "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" build_terrain_factors.py && cd ../..
```

(QGIS의 python-qgis.bat는 공백이 든 경로 인자를 받지 못하므로 scripts 폴더 안에서 실행합니다.)

2단계 물리 모듈(예보·관측을 받은 뒤):

```bash
python "Geo Data Analyst/scripts/fetch_kim_levels.py"
```

```bash
python "Geo Data Analyst/scripts/compute_stage2.py"
```

```bash
python work/update_grid_properties.py
```

```bash
python "Geo Data Analyst/scripts/verify_obs_vs_forecast.py"
```

주기 실행은 2026-10-19에 Windows 작업 스케줄러에 등록했습니다: `Halla-GeoData pipeline`(매시 45분, `RUN_PIPELINE.cmd`)과 `Halla-GeoData train`(일요일 03:00, `RUN_TRAIN.cmd`). 다른 PC에서는 파일 안의 `schtasks` 명령으로 등록합니다.

## 진행 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 지점 메타 정리·셀 매핑, AWS·ASOS 수집기, 지형 파생 인자 | 완료 (2026-10-16) |
| 2 | 이슬점·LCL·푄 모듈 구현, 대시보드에 이슬점·푄 지수 표시 | 완료 (2026-10-17): KIM 등압면 연결, 색상 기준 3개(셀 이슬점·LCL−셀 고도·푄 지수), 강조 레이어 2개(푄 조건·운무 가능) |
| 3 | 지점 기준 검증: 물리값 대 AWS, 선형 보정 대조군 대비 개선 | 진행 중 (2026-10-17): 검증 파이프라인·누적 아카이브 가동, 지점기압 모듈 검증 완료, 푄 사례 목록 확보. 통계는 수 주 누적 뒤 유의 |
| 4 | KIM 등압면 연결, RF·GBM 학습, 지점 제외 교차검증 | **첫 모델 저장·셀 적용 (2026-10-18, 예비)**: 재분석 짝 자료 13.4만 행(해안 ASOS 4 + 산지 AWS 4)과 실시간 80행으로 학습. 기온 RF 지점제외 RMSE 1.40 °C(물리 1.41), 시간분리 1.28(1.47); 이슬점 GBM 1.88(2.26), 1.86(2.43). 실시간 행 2,000 이상 쌓이면 예비 표시 해제 |
| 5 | 셀 전역 적용, 신뢰 구간, 사례 검증 | 진행 (2026-10-17): 푄 사례 검증으로 적용 규칙 보정(30 % 블렌드, 11–16시), 상류 능선 탐색 60 km로 확장, 셀 상세에 고도대별 ±RMSE 표시, 안개·호우 사례 목록. 학습 모델의 셀 적용은 자료 누적 후 |

첫 물리 점검(1회차, 38지점, 2026-10-16 00:45 KST): 감률 보정으로 기온 RMSE 1.92 → 1.71 °C, 700 m 이상 8지점 2.6 → 1.96 °C. 이슬점 RMSE 5.0 °C로 고지대 예보 습도 오차가 크며 2단계의 과제입니다. 결과는 `data/obs_vs_forecast_check.json`에 있습니다.

## 2단계 물리 모듈 (구현 내용)

- **이슬점**: 5 km 점의 T1H·REH에서 Magnus 식으로 이슬점을 구하고 이슬점 감률 2 °C/km로 셀 고도에 맞춥니다(셀 기온을 넘지 않도록 제한). 색상 기준 "셀 이슬점", 기존 "기온−이슬점 차"도 이 값을 씁니다.
- **LCL**: 점 고도 + 125 m × (T − Td). 색상 기준 "LCL − 셀 고도"가 0 이하면 셀이 구름 속에 있을 가능성이 큽니다. 운무 가능 셀 = LCL 이하 또는 기온−이슬점 ≤ 1 °C (강조 레이어).
- **횡단 바람**: KIM 국지모델 850 hPa 바람(`fetch_kim_levels.py`)을 쓰고, 없으면 초단기예보 10 m 바람을 씁니다.
- **푄**: 횡단 풍향의 16방위에서 셀의 상류 최고고도(`up_max`)와 거리(`up_dist`)를 꺼내고, 그 거리만큼 풍상측으로 옮긴 위치의 5 km 예보점을 상류 공기로 잡습니다. 상류 공기를 LCL까지 건조단열(9.8 °C/km), 능선까지 습윤단열(기온·기압에 따른 포화단열감률, 50 m 간격 적분)로 올린 뒤 셀 고도까지 건조단열로 내립니다. 응결된 수증기는 제거하고 하강 중 이슬점은 1.8 °C/km로 올립니다. 푄 지수 = 푄 계산 기온 − 단순 감률 보정 기온. 푄 조건 = 능선 통과 시 응결 + 바람그늘 깊이 ≥ 300 m + 횡단 풍속 ≥ 5 m/s + 지수 ≥ 1 °C (강조 레이어, 셀 상세에 상류 점·능선·LCL·계산 기온·습도 표시).
- 참조 구현은 `scripts/physics_modules.py`, 라이브 구현은 대시보드 자바스크립트이며 같은 식을 씁니다.

## 3단계 지점 검증 (구성)

- **누적 검증**: `RUN_PIPELINE.cmd`를 매시 실행하면 지점 42개(격자 안 38개)마다 원값(5 km 값 그대로, 무보정 대조군)·감률 보정(선형 대조군)·푄 반영 추정 기온과 이슬점이 관측과 함께 로컬 아카이브(`runtime/kma/verification/stationwise.csv`)에 쌓이고, `data/verification_summary.json`에 고도대(<300, 300–1000, ≥1000 m)·시각·푄 조건별 편향·RMSE와 원값 대비 개선율이 갱신됩니다. 첫 실행(2026-10-17 08:30 발표)에서는 감률 보정이 원값 대비 RMSE 10 % 개선이었고, 이슬점은 RMSE 4.4 °C로 큰 편향(+1.6 °C)을 보였습니다.
- **지점기압 모듈**: 해면기압 → 셀 고도 정역학 환산(층 평균기온, 가온도)을 ASOS 4지점 3년 자료 13만 시간으로 검증해 RMSE 0.17 hPa, 고지대 AWS(윗세오름 1,676 m 등)에서 0.2–0.3 hPa였습니다. 대시보드 색상 기준 "지점기압 (추정)"은 ASOS 해면기압 평균과 셀 기온·이슬점으로 이 식을 적용합니다.
- **푄 사례 목록**: ASOS 동서(성산↔고산)·남북(제주↔서귀포) 쌍에서 풍상 풍속 ≥ 6 m/s, 풍하 기온 +3 °C 이상, 습도 15 %p 이상 하락 조건으로 2023년 이후 145건을 선별했습니다. 3–5월에 집중되고 서풍 때 성산이 풍하인 경우가 104건으로 가장 많습니다. 5단계 사례 검증의 라벨이며, 해안 지점 기준 선별이라 산지 사면 푄은 포착하지 못합니다.

## 4단계 잔차 학습 (구성)

- **학습 대상**: 관측 − 물리 추정(잔차). 기온은 감률 보정 기온, 이슬점은 감률 보정 이슬점을 기준으로 합니다. 최종 추정 = 물리값 + 학습된 잔차.
- **입력 특징** 37개: 시각·계절, 지점·셀·점 고도와 차이, 경사·경사향·집중도, TPI·하늘개방도·해안 거리, 횡단 풍향의 상류 능선·바람그늘, 초단기예보(기온·습도·풍속·풍향·강수·하늘·강수형태), KIM 850·925 hPa(기온·습도·바람), 물리값(감률 기온·이슬점, LCL, 푄 지수·조건).
- **모델**: 릿지 회귀(논문의 선형 대조군), 랜덤포레스트, 히스토그램 그래디언트 부스팅. 5,000행 이상이면 소형 MLP 추가 예정.
- **검증**: 지점 제외 교차검증(GroupKFold, 모든 지점이 한 번씩 검증)과 시간 분리(마지막 20 % 회차). 지표는 최종 추정의 편향·RMSE를 물리값 단독과 비교.
- **저장 임계치**: 2,000행·20지점·48회차 이상일 때만 모델을 저장하고 셀에 적용합니다. 그 전에는 보고서에 `insufficient_data`로 표시되고 교차검증은 코드 점검용입니다. 매시 파이프라인이 돌면 약 3일(≈ 48회차 × 38지점 = 1,800행)부터 조건을 넘습니다.
- **셀 적용**: `apply_residual_model.py`가 전 셀의 특징(지점 고도 = 셀 평균고도)으로 잔차를 예측해 `ml_cells.json`에 쓰고, 대시보드 색상 기준 "학습 보정 기온 / 이슬점"이 이를 표시합니다(모델이 없으면 비활성).

## 5단계 사례 검증과 신뢰 구간 (구성·결과)

- **푄 사례 검증** (`foehn_case_validation.py`): ASOS 동서·남북 쌍에서 풍상 풍속 6 m/s 이상의 횡단 바람 9,359시간에 대해 풍상 지점 공기를 능선(지점 연결선 2 km 이내 최고 셀, 약 1,921 m)을 넘겨 풍하 지점 고도로 내린 공기덩이 값을 관측과 비교했습니다.
  - 선별된 푄 사례 303시간: 공기덩이 기온 RMSE 2.6 °C(감률 4.5, 지속 4.7), 습도 RMSE 16 %p(감률 27). 사례에서는 모듈이 크게 낫습니다.
  - 그 밖의 횡단 바람 9,056시간: 공기덩이 값을 그대로 쓰면 +5.1 °C 과대(능선이 LCL보다 높아 응결로 판정되는 시간이 99.8 %). 즉 "응결 가능"만으로 푄을 적용하면 안 됩니다.
  - 사례는 거의 낮(12–18시)이고 풍상 맑음 비율 51 %(그 밖 19 %)로, 해안 풍하 승온의 상당 부분은 일사 차이입니다. 게이트·블렌드 탐색 결과 "11–16시에 공기덩이 값 쪽으로 30 %만 이동"이 전 시간 RMSE 2.08 → 2.01 °C로 가장 좋았고, 이를 `physics_modules.FOEHN_BLEND/FOEHN_HOURS`와 대시보드에 적용했습니다. 푄 지수와 강조 레이어는 진단용으로 유지합니다.
- **상류 능선 탐색 60 km**: 25 km 창에서는 해안 셀이 한라산을 보지 못해(성산 서쪽 805 m) 60 km로 넓혔습니다(성산 서쪽 1,519 m, 33.5 km).
- **신뢰 구간**: `verify_stations.py`가 고도대별 물리 추정 RMSE를 `uncertainty.json`에 쓰고, 셀 상세에 "추정 불확실성 ±RMSE(편향, 건수/회차)"로 표시합니다. 회차가 쌓일수록 값이 안정됩니다.
- **안개·호우 사례** (`asos_case_catalogue.py`): 안개 2,058시간(4–7월 집중, 고산·제주·서귀포), 호우 167시간(5–9월, 성산·서귀포). 운무 규칙(기온−이슬점 ≤ 1 °C)의 해안 지점 재현율은 48 %, 정밀도 8.7 %로 낮아 해안 안개(이류무)는 이 규칙만으로 잡기 어렵고 시정·천리안 안개 산출물이 필요합니다.

## 첫 잔차 모델 결과 (2026-10-18, 예비)

| 목표 | 물리값 RMSE | 지점 제외 교차검증 RMSE | 시간 분리 RMSE (물리 → 모델) | 저장 모델 | 중요 특징 |
|---|---|---|---|---|---|
| 기온 | 1.41 °C (편향 +0.04) | 릿지 1.58 · RF **1.40** · GBM 1.46 | 1.47 → 1.28 | RF | 시각, 계절, LCL, 감률 기온·이슬점 |
| 이슬점 | 2.26 °C (편향 +1.10) | 릿지 2.74 · RF 1.98 · GBM **1.88** | 2.43 → 1.86 | GBM | 시가지·수목 비율, 계절, 경사향 집중도, 감률 이슬점 |

학습 자료는 재분석(Open-Meteo ERA5, 차선) 입력과 짝지은 해안 ASOS 4지점 3년치 13.3만 행에 PR #17 수집기의 산지 AWS 4지점(어리목·성판악·삼각봉·사제비) 1,481행, 실시간 예보 입력 80행을 더한 것입니다. 지점 수(42)와 행수는 임계치를 넘지만 산지 표본이 적고 입력이 재분석이라 **예비 모델**로 표시합니다. 실시간 행이 2,000개를 넘으면(매시 파이프라인 약 2일) 표시가 풀리고, 포털 AWS 과거 CSV가 들어오면 산지 표본이 수백 배로 늘어납니다. 대시보드 색상 기준 "학습 보정 기온 / 이슬점"이 켜졌고, 셀 상세에 물리값 대비 보정량과 교차검증 RMSE가 나옵니다.

## 한계와 표기

- 모든 산출은 분석용이며 기상청 공식 예보·특보를 대신하지 않습니다.
- 5 km 예보값은 셀 경계에서 계단식으로 바뀌고, 10 m 바람은 지형 가림을 반영하지 않습니다.
- 관측이 없는 셀의 오차는 지점 제외 교차검증으로만 추정할 수 있습니다.
- 기상청 자료는 기상청 API허브 이용약관을, Copernicus DEM은 원 제공자 표기를 따릅니다(저장소 `DATA_SOURCES.md`).
