# 자료 출처와 해석 범위

| 자료 | 사용 범위 | 출처·확인 기록 |
|---|---|---|
| Copernicus GLO-30 DSM | 고도·경사각·사면방향 | `work/public_sources/copernicus_N33_E126.tif`, 다운로드 매니페스트의 원 URL·SHA-256 |
| Esri World Imagery | 기존 위성/항공 배경 | `work/public_sources/esri_service.json`, `satellite_export.json`, `satellite_extent.json` |
| 기존 OSM 기반 벡터 | 탐방로·공원·지명 | `inputs/reference/hallasan_course_cells.gpkg` 및 결과 메타데이터 |
| 기존 LCC 500m 참고격자 | 분석 범위와 집계 단위 | 공식 기상청 격자 정렬 미확인; 계산 결과는 참고격자 ID로 식별 |
| 기상청 레이더 | 문서에 근거한 수집 코드 | 실제 관측자료·키 미포함, 실응답 미검증 |
| AWS 순서 PNG | 사용 안내 | 설명용 생성 이미지, 실제 콘솔 화면을 보증하지 않음 |

## 원 제공자 링크

- [Copernicus DEM AWS 등록 정보](https://registry.opendata.aws/copernicus-dem/)
- [사용 타일](https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N33_00_E126_00_DEM/Copernicus_DSM_COG_10_N33_00_E126_00_DEM.tif)
- [Copernicus DEM 이용조건 원문](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf)
- [Esri World Imagery 서비스·저작권 표시](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer)
- [OpenStreetMap 저작권 및 ODbL 안내](https://www.openstreetmap.org/copyright)
- [기상청 레이더 API 문서](https://apihub.kma.go.kr/apiList.do?seqApi=5)

이 저장소의 자료를 외부 서비스로 재배포할 때는 원 제공자의 해당 자료 이용조건과 출처 표시를 적용해야 합니다. 기존 문서·메타데이터의 분석 한계도 함께 전달하세요. 이 파일은 외부 데이터에 새로운 라이선스를 부여하지 않습니다.

원자료 출처 표기: produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.
