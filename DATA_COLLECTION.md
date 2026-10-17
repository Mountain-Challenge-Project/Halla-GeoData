# 제주·한라산 기상자료 수집

`weather_collect.py`는 기존 저장소의 `.env`에서 `KMA_API_KEY`를 읽는다. Python 3.10 이상과 표준 라이브러리만 사용한다. 키를 명령행에 넣지 않는다. 키가 있는 `.env`와 운영 수집 결과 `runtime/`는 Git 추적 대상에서 제외된다. 검토한 고정 CSV 수집본은 `outputs/jeju_weather/20261017/`에 별도로 공개한다. 이 고정본은 키 없이 읽을 수 있고 실시간으로 갱신되지 않는다.

## 바로 실행

저장소 폴더에서 실행한다. Windows의 Python Launcher가 설치되어 있으면 `python` 대신 `py`를 사용할 수 있다.

```powershell
python weather_collect.py history --start 2026-09-16 --end 2026-10-15
python weather_collect.py mountain-history --start 2026-09-16 --end 2026-10-15
python weather_collect.py sounding-history --start 2026-09-16 --end 2026-10-15
python weather_collect.py export
python weather_collect.py refresh
```

`history`: 제주 ASOS 4개 지점 시간자료, 제주 AWS 목록의 43개 지점에 대한 강수·최고/최저기온·최대풍속·최대순간풍속 일통계를 수집한다. AWS 목록에는 ASOS 4개 지점도 포함된다. 47개의 서로 다른 관측소라는 뜻이 아니다.

`mountain-history`: 현재 AWS 지점 목록에서 노장 해발고도 700m 이상인 8개 지점(어리목·성판악·삼각봉·사제비·영실·진달래밭·윗세오름·한라산남벽)을 선택한다. 하루씩 요청하고, 응답이 잘렸을 때 6시간 구간으로 분할한다. 기본 동시 요청은 2개다. 중단 후 같은 명령을 실행하면 기존 원자료를 재사용한다. 결측이나 계속 실패한 구간까지 채웠다는 의미는 아니므로 품질 파일을 확인한다.

`sounding-history`: 국가태풍센터 47186의 03·09·15·21시 KST(18·00·06·12 UTC) 관측을 요청한다. 관측소 이전 이력은 별도 확보 대상이다.

`refresh`: 최신 ASOS·AWS 관측과 한라산 기준점(126.5357°E, 33.3610°N)의 초단기·단기예보를 수집하고 CSV 및 `latest/latest.json`까지 갱신한다. 전국 AWS 일괄 조회에 실패하면 제주 지점별 조회로 전환한다. API에서 가장 가까운 예보 격자를 조회해 확인한 번호는 **nx=54, ny=36**이다. 이 한 격자의 예보를 한라산 500m 전역의 예보로 간주하면 안 된다.

```powershell
# 저장된 자료로 CSV·품질표만 재작성: 네트워크/키 사용 없음
python weather_dataset.py

# 최신 레이더 누적강수 1개와 공식 PCP 좌표 파일 요청
python weather_collect.py radar

# 좌표 파일만 재확인
python weather_collect.py coordinates --timeout 60

# 받은 레이더와 좌표로 제주 주변 원격자점 CSV 생성 (GDAL·NumPy 필요)
& 'C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat' -X utf8 weather_radar_csv.py
python weather_collect.py export

# 작은 연결 확인 및 별도 권한 확인
python weather_collect.py probe
python weather_collect.py extended

# 오프라인 테스트
python -m unittest discover -s tests -v

# 공개 고정본의 파일 해시·행수·최신 CSV 참조 검증 (키/네트워크 불필요)
python work/package_weather.py --verify-only
```

이 작업은 Windows 작업 스케줄러나 클라우드의 상시 실행을 등록하지 않는다. 주기 실행 환경에서 `refresh`를 호출할 수 있다. 호출 주기는 계정 한도와 원자료 갱신주기에 맞춰 정하고, 중복 프로세스 실행은 피한다. AWS 전체 지점 수집이 실패하는 날에는 갱신에 수 분이 걸릴 수 있다.

## 저장 위치와 사용 순서

기본 폴더는 `runtime/jeju_weather_collection/`이다. `--output`으로 변경할 수 있다. `history` 또는 `probe`를 먼저 실행해 지점 메타데이터를 확보한다.

| 파일/폴더 | 내용 |
|---|---|
| `csv/stations_sfc.csv`, `csv/stations_aws.csv` | API 지점 목록에서 제주 주소를 선택한 좌표·고도·센서 높이 |
| `csv/asos_hourly_*_raw.csv` | 46개 ASOS 원래 필드와 KST/UTC 시각 |
| `csv/asos_hourly_*.csv` | 주요 변수를 단위가 드러나는 이름으로 정리한 시간자료 |
| `csv/aws_daily_*.csv` | 날짜·지점·변수별 긴 형식의 일통계 |
| `csv/aws_minute_*_raw.csv` | AWS 매분 원래 필드. 음수 결측코드 포함 |
| `csv/aws_minute_*.csv` | AWS 매분 주요 변수·품질 플래그 |
| `csv/aws_hourly_snapshot_*.csv` | 매 정각의 표본. 시간평균으로 계산한 자료가 아님 |
| `csv/sounding_47186_history.csv` | 국가태풍센터의 원래 연직 관측층. 결측 원값과 정리값 병기 |
| `latest/*.csv` | 사용자가 열어볼 최신 성공 자료 |
| `latest/latest.json` | 웹/QGIS 연동용 성공 시각·지연 상태·버전별 CSV 경로 |
| `snapshots/` | 매 갱신 시 불변 CSV. 이 파일들을 쓴 뒤 manifest를 원자적으로 교체 |
| `raw/` | 서버 응답 원본. 실패·잘림 여부는 로그와 품질 기록을 함께 확인 |
| `requests.jsonl` | 인증키를 제외한 요청 인자·HTTP 상태·수신시각·SHA256 |
| `api_status.csv` | endpoint별 실제 호출 상태. HTTP 성공과 파싱 성공은 별개 |
| `file_inventory.csv` | 데이터셋별 행수·지점수·시간 범위·파일 해시 |
| `quality/station_variable_availability.csv` | 지점×변수별 수신/기초검사 통과/결측 수 |
| `quality/daily_missing_records.csv` | 일통계에서 아예 반환되지 않은 날짜·지점·변수 조합 |
| `quality/sounding_profiles.csv` | 수신한 연직 프로파일별 관측층 개수 |
| `quality/parse_validation.json` | CSV로 해석하지 못한 응답 목록 |
| `collection_summary.json` | 수집 결과와 API 상태 요약 |

CSV는 Excel에서 한글을 읽을 수 있는 UTF-8 BOM이다. 수치 결측은 빈칸으로 저장하고 `qc_flags` 또는 원값을 함께 보관한다. 반환되지 않은 시각을 인위적으로 행으로 만들거나 보간하지 않는다.

최신 관측 요청은 현재보다 10분 전, 초단기예보는 현재보다 45분 전을 기준으로 제공시각을 선택한다. 지연 판정값은 프로젝트의 제안 설정(ASOS 90분, AWS 60분, 초단기 2시간, 단기 4시간)이며 제공기관의 SLA가 아니다. `stale_at_publish`는 manifest 작성 당시 판정이다. 화면에서는 현재시각과 각 행의 관측/발표시각을 비교해 지연 여부를 다시 계산해야 한다.

## 변수와 시간 해석

ASOS의 풍향 WD는 36방위 원값을 10배해 도 단위로 바꾼다. 0은 무풍/방향 코드로 구분해 방향값을 비운다. AWS WD10은 이미 도 단위이며 360은 원자료 도움말의 무풍 코드다. 10분 평균풍과 최대순간풍을 구분한다.

ASOS PA는 현지기압, PS는 해면기압이다. AWS도 둘을 별도 칼럼으로 둔다. 기압계 해발고도와 노장 고도는 다르며, AWS 지점 목록 응답에는 기압계·온도계·우량계 높이가 없어서 빈칸으로 남겼다. 일부 고지대 관측소의 습도·기압은 결측일 수 있다. 기초 범위검사를 통과해도 교정이나 독립 검증을 마친 값은 아니다.

ASOS RN은 4~10월 1시간, 11~3월 3시간 누적이다. 이번 기간은 1시간 누적에 해당한다. RN의 음수값은 0으로 채우지 않았고 IR 강수유무 코드를 함께 보관했다. 시정 VS는 원래 10m 단위이므로 10배해 m로 변환한다.

AWS RN_15m/RN_60m/RN_12h는 서로 겹치는 누적구간이다. 연속 시각 값을 그대로 더하지 않는다. RN_DAY는 일누적이다. `aws_hourly_snapshot`은 00분의 자료를 선택한 것으로 기온의 시간평균이 아니다. 지점 비교 시 관측 평균시간 차이를 고려해야 한다.

레이더 PCPH는 누적강수다. `unit=MM` 응답의 비음수 원값에 0.01을 곱하면 mm가 된다. 이것을 순간 강우강도 mm/h로 이름만 바꿔 쓰면 안 된다. 원자료의 -30000/-25000/-20000 등은 의미 확인 전 그대로 남긴다. 공식 PCP 격자 좌표의 수신·검증을 완료하기 전에는 기존 가정 LCC 500m 격자에 레이더값을 강제로 대응시키지 않는다. `radar_validation.json`은 격자 구조 검사 결과이며 공간 정렬/결측 의미 검증 결과와 별개다.

관측은 KST와 UTC를 함께 저장한다. 연직 관측 API 요청 시간은 UTC다. 예보는 실제 응답의 발표시각과 유효시각을 각각 저장한다. `available_at_utc`는 제공기관의 실제 공개시각을 알 수 없어 비워 두고, 실제 수신시각만 기록한다. 과거 관측을 오늘 받아 구성한 학습자료는 당시 실시간으로 확보했던 자료와 다르다. 예보 과거 30일 전체 발행본은 아직 확보하지 않았으며, 수집 시점의 발행본부터 원본을 보존한다.

## 기존 공간자료 연결

수집 당시 참조한 지형은 한라산 1,849개·제주 7,519개 격자와 탐방로였다. 공개 `static_inventory.csv`에 당시 `source_git_revision`·`repo_path`·해시를 보관한다. 현재 저장소는 이후 공식 레이더 정의로 제주 격자를 7,518개로 갱신했으므로 과거 격자와 혼용하지 않는다. 이번 기상 CSV는 어느 격자에도 조인하지 않았다. 현행 지도·기압/푄 모델은 `Geo Data Analyst/README.md`와 루트 README를 참조한다. Copernicus GLO-30은 DSM이며 VWorld 화면 분석값이 아니다. 경사도는 지표면 경사이고 탐방로 진행방향의 보행 경사와 다르다. World Imagery는 배경 영상이며 기상 관측 또는 경사 계산 입력이 아니다.

점 관측은 관측소 좌표로 표시한다. 지형·능선·풍상/풍하 효과를 반영한 공간 보정 및 독립 검증을 하기 전에는 점 관측을 500m 전역의 정답으로 확대하지 않는다. 예보 한 격자·레이더 원격탐사·지점 센서의 해상도와 측정 대상을 구분한다.

## 공식 근거

- 지상관측과 ASOS 시간자료: https://apihub.kma.go.kr/apiList.do
- AWS 매분/시간/일 통계: https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239
- 지점 정보: https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=317
- 고층 관측 API: https://apihub.kma.go.kr/apiList.do?seqApi=4
- 고층 관측망과 현재 관측시각: https://www.kma.go.kr/kma/biz/observation03.jsp
- 초단기·단기예보: https://apihub.kma.go.kr/apiList.do?seqApi=10&seqApiSub=286
- 레이더 누적강수와 PCP 좌표: https://apihub.kma.go.kr/apiList.do?seqApi=5
- 위성 지점 산출물: https://apihub.kma.go.kr/specialApiList.do

기상자료 출처는 기상청 API허브다. 운영 응답 원본과 로그는 로컬에 보관하고, 이번 고정 CSV와 품질/호출 결과 요약은 저장소에 공개한다. 메타데이터의 `raw_file` 경로는 로컬 원본 참조이며 해당 HTTP 원본이 Git에 들어 있다는 뜻이 아니다. `_raw.csv`는 원래 필드의 CSV 표현이다. 정적 지형·탐방로는 중복 복사하지 않고 `static_inventory.csv`의 `repo_path`로 기존 저장소 파일을 참조한다.

고정본 목록·행수·미수집 항목은 [README](README.md#제주-국지기상-데이터-수집)와 동봉 CSV를 기준으로 한다. 해당 상태는 이번 수집본에 한정되며 별도 모델 파이프라인의 KIM·푄 후보 목록·특보 산출물 상태가 아니다. 공개 폴더에는 HTTP 원본 전체가 없으므로 `weather_dataset.py`의 재생성 입력으로 지정하지 않는다. 재수집은 로컬 `runtime/`에서 수행한다. `work/package_weather.py --input <로컬 수집 폴더> --output <새 고정본 폴더> --static-source-revision <지형 원본 Git 커밋>`은 검토한 catalog·dictionary·static inventory가 있는 수집 결과만 내보내며 기존 고정본을 덮어쓰지 않는다.

재배포/서비스 공개 시에는 기상청 자료 출처 표시와 해당 API·공간자료의 이용조건을 확인한다. 403은 해당 요청의 권한/인증 응답으로 기록하며, 계정 전체의 승인 여부를 단정하지 않는다.
