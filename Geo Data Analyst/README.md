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
| `scripts/RUN_OBS.cmd` | 관측 수집 주기 실행용 배치 (작업 스케줄러 등록 예시 포함) |
| `data/kma_stations_jeju.csv`, `.geojson` | 제주 지점 42개(ASOS 4): 좌표, 노장고도, DSM 고도, 속한 셀, 셀 고도·경사 |
| `data/jeju_grid_terrain_factors.csv` | 셀 7,518개의 TPI·하늘개방도·해안 거리·16방위 상류 최고고도/거리 |
| `data/obs_vs_forecast_check.json` | 첫 물리 점검 결과 (지점별 관측·추정값, 통계) |

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
| 정답 | AWS 1분(제주 42지점), ASOS 시간(4지점), 지점정보, 제주 라디오존데(47186) | API 승인, 수집 중. ASOS는 2023-01부터 소급 수집 완료(로컬) |
| 격자 입력 | 초단기예보·실황, 단기예보, 레이더 PCPH·HSR, AWS 객관분석 격자, KIM 등압면, 천리안 2A L2, 특보 | API 승인 |
| 격자 입력 | KIM 지상 2D, 낙뢰 | 활용신청 대기 |
| 지형 | 셀 고도·경사·경사향·집중도, TPI, 하늘개방도, 해안 거리, 16방위 상류 최고고도 | 완료 (`grid.geojson`에 결합) |
| 외부 | AWS 과거 분자료(기상자료개방포털 CSV), ERA5, MODIS, Sentinel-3, 토지피복·임상도 | 미수집 (계정 필요, 보고서 5장에 경로) |

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
"C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat" "Geo Data Analyst/scripts/build_terrain_factors.py"
```

```bash
python work/update_grid_properties.py
```

```bash
python "Geo Data Analyst/scripts/verify_obs_vs_forecast.py"
```

관측을 주기적으로 쌓으려면 `scripts/RUN_OBS.cmd`를 Windows 작업 스케줄러에 10분 주기로 등록합니다(파일 안에 명령 예시).

## 진행 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 지점 메타 정리·셀 매핑, AWS·ASOS 수집기, 지형 파생 인자 | 완료 (2026-10-16) |
| 2 | 이슬점·LCL·푄 모듈 구현, 대시보드에 이슬점·푄 지수 표시 | 예정 |
| 3 | 지점 기준 검증: 물리값 대 AWS, 선형 보정 대조군 대비 개선 | 예정 (첫 점검만 수행) |
| 4 | KIM 등압면 연결, RF·GBM 학습, 지점 제외 교차검증 | 예정 |
| 5 | 셀 전역 적용, 신뢰 구간, 사례 검증 | 예정 |

첫 물리 점검(1회차, 38지점, 2026-10-16 00:45 KST): 감률 보정으로 기온 RMSE 1.92 → 1.71 °C, 700 m 이상 8지점 2.6 → 1.96 °C. 이슬점 RMSE 5.0 °C로 고지대 예보 습도 오차가 크며 2단계의 과제입니다. 결과는 `data/obs_vs_forecast_check.json`에 있습니다.

## 한계와 표기

- 모든 산출은 분석용이며 기상청 공식 예보·특보를 대신하지 않습니다.
- 5 km 예보값은 셀 경계에서 계단식으로 바뀌고, 10 m 바람은 지형 가림을 반영하지 않습니다.
- 관측이 없는 셀의 오차는 지점 제외 교차검증으로만 추정할 수 있습니다.
- 기상청 자료는 기상청 API허브 이용약관을, Copernicus DEM은 원 제공자 표기를 따릅니다(저장소 `DATA_SOURCES.md`).
