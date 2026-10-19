# 자료 출처와 해석 범위

| 자료 | 사용 범위 | 출처·확인 기록 |
|---|---|---|
| Copernicus GLO-30 DSM | 고도·경사각·사면방향 | `work/public_sources/copernicus_N33_E126.tif`, 다운로드 매니페스트의 원 URL·SHA-256 |
| Esri World Imagery | 기존 위성/항공 배경 | `work/public_sources/esri_service.json`, `satellite_export.json`, `satellite_extent.json` |
| 기존 OSM 기반 벡터 | 탐방로·공원·지명 | `inputs/reference/hallasan_course_cells.gpkg` 및 결과 메타데이터 |
| 레이더 500m 격자 (한라산·제주) | 분석 범위와 집계 단위 | `inputs/reference/radar_grid_cells.gpkg`; 기상청 레이더 합성 격자 정의(LCC 30/60, 126E/38N, WGS84 타원체, i0=1121/j0=1681)를 공식 좌표 API로 검증해 생성. 제주는 Natural Earth 1:10m 외곽선(퍼블릭 도메인)과 겹치는 셀만 선택. 이전 가정 격자는 `hallasan_course_cells.gpkg`에 기록용으로 보존 |
| Esri World Imagery (제주 범위) | 제주 전역 위성/항공 배경 | `work/public_sources/satellite_jeju*.{jpg,json}`, 다운로드 매니페스트의 원 URL·SHA-256 |
| Copernicus Sentinel-2 L2A (AWS Open Data COG) | 대시보드 날짜 있는 실색 배경, NDVI, 적설 마스크 | Earth Search STAC로 검색, `sentinel-cogs` 버킷에서 /vsicurl 읽기. 사용 장면 ID·날짜·구름 비율은 `outputs/jeju_dashboard/data/s2_meta.json`. "Contains modified Copernicus Sentinel data" 표기 |
| OSM POI·sac_scale | 대피소·화장실·주차장·안내소·AED 점, 등산로 난이도 선 | `work/public_sources/osm_pois_sacscale.json`, `osm_sacscale_geom.json` (Overpass, 매니페스트에 질의문·SHA-256). © OpenStreetMap contributors, ODbL. 현장 상태 미검증 |
| OSM 제주올레 루트 | 올레 코스 참고 선형과 코스별 경사 요약 | `work/public_sources/osm_olle_relations.json`, `osm_olle_ways.json` (Overpass API, 질의문·SHA-256은 매니페스트). © OpenStreetMap contributors, ODbL. 공식 코스 선형이 아니며 OSM에 없는 코스는 `outputs/jeju_slope/olle_coverage.json`에 기록 |
| 기상청 지점정보·AWS 1분·ASOS 정시 관측 | 국지기상 모델의 정답 자료, 대시보드 관측 지점 레이어 | API허브 `stn_inf.php`, `nph-aws2_min`, `kma_sfctm2/3`. 지점 목록은 `Geo Data Analyst/data/kma_stations_jeju.csv`(원 응답 `work/public_sources/kma_stn_inf_*.txt`), 관측값 누적은 로컬 `runtime/kma/obs/`에만 두고 Git 제외. 최신값만 `outputs/jeju_dashboard/data/obs_latest.json` |
| 기상청 KIM 국지모델 등압면 (925·850 hPa) | 푄 모듈 상류 공기·횡단 바람 | API허브 `nwp_nc_prs2d_down.php` group=KIML. 1.5 km 점을 5 km 격자점 평균으로 집계해 `outputs/jeju_dashboard/data/levels.json`에만 두고 원 CSV는 로컬 `runtime/kma/kim/` |
| ERA5-Land·ERA5 (Open-Meteo 아카이브 API) — **차선**, 1순위는 Copernicus CDS 직접 다운로드 | 과거 격자 입력(2023~): 지점별 2 m 기온·이슬점·습도·기압·바람·강수·운량·일사, 925·850 hPa 기온·습도·바람·지위고도 | https://open-meteo.com (CC-BY 4.0, 비상업 무료, 키 불필요). 원자료 © Copernicus Climate Change Service ERA5/ERA5-Land. 파일은 로컬 `runtime/kma/era5/`, 목록·SHA-256은 `Geo Data Analyst/data/era5_openmeteo_manifest.json` |
| ESA WorldCover 2021 (10 m) — **차선**, 1순위는 환경부 세분류 토지피복도 | 셀별 토지피복 비율 (수목·초지·농지·시가지·나지·수역) | https://esa-worldcover.org, AWS Open Data 타일 N33E126 (CC-BY 4.0). 로컬 `runtime/external/`, 매니페스트 `external_rasters_manifest.json`, 셀 집계 `jeju_grid_landcover.csv` |
| ETH 전지구 수관고 2020 (10 m) — **차선**, 1순위는 산림청 임상도 | 셀별 평균·90백분위 식생 높이 | Lang et al. 2023, https://langnico.github.io/globalcanopyheight/ (CC-BY 4.0). 같은 방식 |
| 산림청 임상도 1:5,000 (1순위) | 셀별 산림 비율, 침엽·활엽·혼효, 영급, 밀도, 수고급 | 산림공간정보서비스(https://map.forest.go.kr) 로그인 다운로드, 2021 전산화 속성, EPSG:5179. 원 SHP는 로컬 `runtime/external/fgis_forest/`에만 두고 Git 제외; 셀 집계 `Geo Data Analyst/data/jeju_grid_forest.csv` |
| 기상청 레이더 | 수집 코드와 변환기 | 실응답 2026-10-15 확인(PCPH acc=60). 원자료·GeoTIFF·프레임은 로컬 `runtime/`·`input/`·`dist/frames/`에만 두고 Git 제외. 격자 정의는 `work/public_sources/kma_radar_grid.json` |
| 기상청 지상·고층 관측 및 예보 | 수집 코드와 2026-10-17 고정 CSV 수집본 | `outputs/jeju_weather/20261017/`의 목록·품질표·파일 해시. 30일 관측과 단일 격자 예보. 부분 수집·결측 포함 |
| 기상청 레이더 PCPH 및 공식 PCP 좌표 | 제주 주변 원격자점 CSV 한 시각 | 2026-10-16 08:05 KST 종료 60분 누적강수. 음수코드 의미·기존 500m 격자 정렬·독립 위치 검증 미완료 |
| AWS 순서 PNG | 사용 안내 | 설명용 생성 이미지, 실제 콘솔 화면을 보증하지 않음 |

## 원 제공자 링크

- [Copernicus DEM AWS 등록 정보](https://registry.opendata.aws/copernicus-dem/)
- [사용 타일](https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N33_00_E126_00_DEM/Copernicus_DSM_COG_10_N33_00_E126_00_DEM.tif)
- [Copernicus DEM 이용조건 원문](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf)
- [Esri World Imagery 서비스·저작권 표시](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer)
- [OpenStreetMap 저작권 및 ODbL 안내](https://www.openstreetmap.org/copyright)
- [Overpass API](https://overpass-api.de/) (OSM 루트 릴레이션·길 다운로드 경로)
- [Natural Earth 1:10m Admin 0](https://www.naturalearthdata.com/) (제주 외곽선, 퍼블릭 도메인)
- [기상청 레이더 API 문서](https://apihub.kma.go.kr/apiList.do?seqApi=5)
- [기상청 지상관측 API 문서](https://apihub.kma.go.kr/apiList.do)
- [기상청 AWS API 문서](https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239)
- [기상청 고층관측 API 문서](https://apihub.kma.go.kr/apiList.do?seqApi=4)
- [기상청 초단기·단기예보 API 문서](https://apihub.kma.go.kr/apiList.do?seqApi=10&seqApiSub=286)

기상자료 출처: **기상청 API허브**. 원 제공자 단위를 유지하고, 시간대·결측코드 처리 및 정규화 방법을 `DATA_COLLECTION.md`에 기록했습니다. 원자료 응답 전체와 인증키는 Git에 포함하지 않습니다. `_raw.csv`는 원래 필드 확인용 CSV이며 HTTP 원본 파일은 아닙니다. 공개 CSV의 고정 시각과 품질 한계를 함께 전달하고, 제공기관의 최신 이용조건을 따르세요. 이 저장소는 외부 기상자료에 별도의 무제한 이용허락을 부여하지 않습니다.

이 저장소의 자료를 외부 서비스로 재배포할 때는 원 제공자의 해당 자료 이용조건과 출처 표시를 적용해야 합니다. 기존 문서·메타데이터의 분석 한계도 함께 전달하세요. 이 파일은 외부 데이터에 새로운 라이선스를 부여하지 않습니다.

원자료 출처 표기: produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.
