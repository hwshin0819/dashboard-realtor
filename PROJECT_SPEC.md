# 이실장 사업팀 대시보드 — 재구성용 스펙 문서

이 문서는 이 프로젝트를 **처음부터 다시 만들어야 할 때** (새 노트북/새 계정에서, 기존 코드 없이)
Claude Code에게 그대로 던져줄 수 있는 요청서입니다. "무엇을, 왜" 만들어야 하는지와 핵심 수치/스키마를
정확하게 담았습니다. 실제 코드가 남아있다면 이 문서 없이 코드만 복사하면 되고, 이 문서는 코드가
전혀 없는 최악의 상황을 대비한 것입니다.

---

## 0. 한 줄 요약

부동산 중개업(공인중개사) 시장을 모니터링하는 사내 Streamlit 대시보드. 국토부/한국부동산원/통계청/
국세청 공개데이터 + 자체 수집한 개업공인중개사 현황(브이월드 API)을 합쳐서 보여주고, 로그인 기반
권한 관리와 B2B 영업 리드 추출 기능이 있음. Windows 로컬 PC에서 Streamlit 서버로 상시 구동, 사내
LAN으로 동료들이 접속.

---

## 1. 기술 스택 & 환경설정

- Python 3.14, `venv`(`.venv` 폴더), Windows.
- `requirements.txt`:
  ```
  streamlit>=1.38
  pandas>=2.0
  plotly>=5.20
  requests>=2.31
  openpyxl>=3.1
  PublicDataReader>=1.1.1
  python-dotenv>=1.0
  xmltodict>=0.14
  beautifulsoup4>=4.13
  ```
  **중요 설치 순서 이슈**: `PublicDataReader`가 `pandas==2.2.3` 등 구버전을 강하게 요구하는데, 최신
  Python에선 그 pandas 버전이 소스빌드만 되고 한글 경로/로케일 때문에 빌드가 실패한다. 해결책:
  `pip install --no-deps PublicDataReader` 로 의존성 체크 없이 설치하고, 실제 필요한
  `python-dotenv`/`xmltodict`/`beautifulsoup4`는 따로 설치한다.
- 필요한 비밀값 2곳:
  - `.env` (프로젝트 루트): `DATA_GO_KR_SERVICE_KEY=` (공공데이터포털, 국토부 실거래가 API 8종 공통),
    `R_ONE_SERVICE_KEY=` (한국부동산원 R-ONE — 현재는 미사용, 향후 대비용으로만 보관).
  - `data/vworld_secrets.json`: `{"key": "<브이월드 API 키>", "domain": "<등록한 도메인>"}` — 브이월드
    "부동산중개업사무소정보조회" API 키. 이 파일이 없으면 `vworld_client.py`가 즉시 `SystemExit`.
- 로컬 실행: `streamlit run app.py --server.address 0.0.0.0 --server.port 9000` (사내 LAN에서 접속
  가능하도록 `0.0.0.0` 바인딩, 고정 포트 9000). `run.bat`(최초 설치+실행용, venv 생성/pip install까지
  다 해줌), `run_hidden.bat`(콘솔 없이 무한 재시작 루프, 크래시하면 5초 후 재시작), `start_hidden.vbs`
  (윈도우 시작프로그램 등록용, 창 안 뜨게 `run_hidden.bat` 실행).
- `.claude/launch.json`으로 Claude Code 프리뷰 도구가 `.venv\Scripts\streamlit.exe run app.py
  --server.port 9000 --server.headless true`를 실행하도록 등록.

---

## 2. 데이터 소스 (외부 공공데이터 3계통 + 자체 수집)

1. **브이월드(VWorld) 국가중점데이터 API — 부동산중개업사무소정보조회(`getEBOfficeInfo`)**
   `https://api.vworld.kr/ned/data/getEBOfficeInfo`. 상태코드 4종만 조회 가능: `1`=영업중,
   `2`=휴업, `3`=휴업연장, `8`=업무정지 (실효/전출/등록취소는 API가 아예 목록에서 뺌 → 폐업은
   "어제 있었는데 오늘 없어짐"으로 판정해야 함). 페이지당 1000건, `pageNo`로 페이지네이션.
2. **국토교통부 실거래가 공개시스템 (공공데이터포털, `PublicDataReader` 라이브러리로 호출)** —
   아파트/오피스텔/연립다세대/단독다가구 × 매매/전월세 = 8개 API. 시군구 코드+월 단위로만 조회
   가능(한 번에 여러 달/여러 지역 조회 불가) → 전국 5개년 백필은 시군구(약 250개)×유형(4)×
   거래유형(2)×개월수 조합을 전부 순회해야 해서 매우 느림(재개 가능한 배치로 설계해야 함, 아래
   4번 참고).
3. **통계청 서비스업조사(KSIC 68221, 부동산 중개 및 대리업) + 국세청 국세통계포털(TASIS)** — 이
   둘은 API가 아니라 **수작업으로 받아서 하드코딩/JSON으로 박아넣은 정적 데이터**임 (연 단위라
   자주 안 바뀜). 통계청 데이터는 연도별 매출액/사업체수/종사자수 등 표를 그대로 코드에 리스트로
   박아둠(2020년은 조사 방식이 바뀌어 결측). TASIS는 비공개(비공식) 엔드포인트
   (`wqAction.do?actionId=ATWEPFLA001R03`, 파라미터 `YR`=2021~2025)로 긁어서
   `data/tasis_lifestyle_058.json`에 저장해두고 그 파일만 읽음 — "매출은 그 전해 귀속소득 기준"이라는
   1년 시차 규칙이 있음(YR=2025는 사업자수는 2025년말 기준, 매출은 2024년 귀속분).
4. **한국부동산원 R-ONE** — 조사만 하고 **채택 안 함**. 매매 거래량은 이미 전국/시도별로
   사전집계돼 있어 국토부보다 훨씬 빠르게 가져올 수 있지만(API `SttsApiTblData.do`, `STATBL_ID`
   지정, `CLS_ID`로 지역 필터), **전월세 거래량 통계 자체가 없고**, "주택" 분류에 오피스텔이
   빠져있어(비아파트 정의가 국토부 쪽과 어긋남) 기존 파이프라인과 정의를 통일하기 어려워서
   포기함. `.env`에 키만 남겨둠.

---

## 3. SQLite 스키마 (`db.py`, 파일: `data/offices.db`)

`get_conn()`은 호출될 때마다 `CREATE TABLE IF NOT EXISTS` 전체를 실행(멱등) — 마이그레이션 스크립트
불필요, 스키마에 테이블만 추가하면 자동 반영.

```sql
CREATE TABLE IF NOT EXISTS offices (
    jurirno TEXT PRIMARY KEY,          -- 법인/사업자 고유번호
    ld_code TEXT, ld_code_nm TEXT,     -- 법정동 시군구 코드/이름
    bsnm_cmpnm TEXT,                   -- 상호명
    brkr_nm TEXT,                      -- 개설중개사명
    sttus_se_code TEXT, sttus_se_code_nm TEXT,
    regist_de TEXT, estbs_begin_de TEXT, estbs_end_de TEXT,
    last_updt_dt TEXT,
    mnnmadr TEXT, rdnmadr TEXT, rdnmadr_code TEXT,
    first_seen_date TEXT, last_seen_date TEXT,
    closed_date TEXT                  -- NULL이면 영업 중으로 간주
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT, jurirno TEXT,
    event_type TEXT,                  -- 'open' | 'close' | 'status_change'
    from_status TEXT, to_status TEXT,
    ld_code TEXT, ld_code_nm TEXT, bsnm_cmpnm TEXT
);
-- events(event_date), events(event_type) 인덱스

CREATE TABLE IF NOT EXISTS daily_region_stats (
    date TEXT, region TEXT, active INTEGER, opened INTEGER, closed INTEGER,
    PRIMARY KEY (date, region)
);
CREATE TABLE IF NOT EXISTS legacy_monthly_stats (
    month TEXT, region TEXT, opened INTEGER, closed INTEGER, source TEXT,
    PRIMARY KEY (month, region)
);
CREATE TABLE IF NOT EXISTS agent_quarterly_stats (
    month TEXT, region TEXT, count INTEGER,
    PRIMARY KEY (month, region)
);
CREATE TABLE IF NOT EXISTS collection_log (
    collected_date TEXT PRIMARY KEY,
    total_active INTEGER, total_pause INTEGER, total_ext INTEGER, total_stop INTEGER,
    collected_at TEXT
);
CREATE TABLE IF NOT EXISTS transaction_monthly (
    ym TEXT, sigungu_code TEXT, property_type TEXT, trade_type TEXT,
    count INTEGER, avg_price INTEGER, avg_deposit INTEGER, avg_rent INTEGER,
    PRIMARY KEY (ym, sigungu_code, property_type, trade_type)
);
CREATE TABLE IF NOT EXISTS transaction_collect_progress (
    sigungu_code TEXT, property_type TEXT, trade_type TEXT, ym TEXT,
    status TEXT, updated_at TEXT,
    PRIMARY KEY (sigungu_code, property_type, trade_type, ym)
);
```

`legacy_monthly_stats`는 실측 수집 시작(2026-09) 이전의 과거 월별 통계를 다른 소스에서 가져와
채워둔 것(`import_legacy.py`가 `data/realtor_legacy_data.json`을 읽어 채움), `daily_region_stats`는
2026-09부터 실측 데이터.

---

## 4. 파일 기반 저장소 (`data_store.py`) — `data/` 폴더 밑 JSON/JSONL

- `users.json` — 계정: `{"<id>": {"이름","역할":"admin"|"user","credential":{"salt","hash"},"pages":[...]}}`.
  비밀번호는 **salt+sha256**만 저장(복호화 불가, 관리자가 재설정 기능으로만 바꿔줌 — 셀프 비번변경
  기능은 의도적으로 안 만듦, 그래야 관리자가 항상 비밀번호를 알고 있음).
- `access_log.jsonl` — 한 줄에 하나씩: `{"시각","아이디","동작":"로그인"|"로그아웃","결과":"성공"|"실패","비고","IP"}`.
  `IP`는 `st.context.ip_address`(Streamlit 1.37+ 공식 API) — **로컬(localhost) 접속 시 항상 None**을
  반환하므로 `None`이면 `"로컬(localhost)"`로 대체 저장. 스푸핑 가능해서 보안 용도 아님, 참고용.
- `webhooks.json` / `targets.json` / `schedule.json` — 전부 **UI 데모/설정용이고 실제로 동작하는
  스케줄러가 아님**(진짜 스케줄은 Windows 작업 스케줄러, 아래 6번). `st.data_editor`로 편집.
- `mock_stats.json` — 초기 개발용 목데이터, 실제 페이지에서는 안 씀(레거시).

---

## 5. 인증/권한 시스템 (`auth.py`)

- 계정 없으면 최초 1회 `admin`/`changeme123` 시드 생성.
- 로그인 폼: 아이디 입력창에 **한글 타이핑 즉시 필터링**(정규식 `[ㄱ-ㆎ가-힣]`) —
  모든 계정 아이디가 영문/이메일이라 한글 섞이면 100% 오타이므로 입력 단계에서부터 차단. 구현은
  `st.components.v1.html(..., height=0)`로 만든 iframe에서 `window.parent.document`로 실제 폼의
  input을 찾아 `input` 이벤트에 리스너를 붙이는 방식(React 컨트롤드 인풋이라 네이티브 setter로 값을
  바꾸고 `input` 이벤트를 다시 dispatch해야 화면에 반영됨).
- 로그인 성공/실패/로그아웃마다 `data_store.append_access_log(...)`에 IP 포함해서 기록.
- 페이지 권한: `auth.PAGE_*` 문자열 상수가 사이드바 라벨이면서 동시에 `users.json`의 `"pages"` 배열
  값 — 이 값 자체를 바꾸면 기존 계정도 마이그레이션해야 함. `관리자 계정 관리`/`시스템 접속 로그`는
  `role=="admin"`인 계정에만 자동으로 붙고 `"pages"` 배열과는 무관.
- **사이드바 메뉴는 접근 권한과 무관하게 항상 전체가 보이고, 권한 없는 항목은 회색으로 흐리게만
  표시**(숨기지 않음) — 클릭하면 "접근 권한이 없습니다" 다이얼로그.

---

## 6. 자동 수집 · 백업 (스케줄링)

Windows 작업 스케줄러에 등록된 2개 작업(둘 다 `.venv` 활성화 후 실행하는 `.bat` 래퍼 사용):

1. **`중개사무소_데이터수집`** — 매일 06:00 1회, `collect_daily.bat` → `collector.py`.
   - 브이월드에서 전국 스냅샷을 받아 어제 상태(`offices` 테이블, `closed_date IS NULL`인 것들)와
     비교해 개업/폐업/상태전환 이벤트 생성. 최초 실행(bootstrap, `offices` 테이블이 비어있을 때)은
     이벤트 없이 현재 상태만 저장.
   - `daily_region_stats`, `collection_log` 갱신 후 **DB commit까지 끝내고 나서** 엑셀 내보내기
     (`excel_export.append_daily_stats`)와 백업(`backup.backup_now`)을 시도 — **이 둘은 각각
     try/except로 감싸서 실패해도(예: 엑셀 파일이 열려있어서 PermissionError) 절대 전체를
     죽이지 않음**(과거에 이 부분에서 예외가 나서 스크립트가 죽어 몇 주씩 수집이 멈춘 적 있었음,
     반드시 이 패턴 유지).
   - 엑셀 출력 파일: `data/지역별_일별_통계.xlsx` (시트 `일별_지역별_통계`), 날짜별로 3열
     (영업중/신규등록/폐업) 블록이 옆으로 쌓이는 구조, 1행=전체(전국) 합계, 그 아래 지역별.
   - 백업: `data/backups/YYYY-MM-DD/`에 `offices.db` + 엑셀 파일 통째로 복사, 30일 지난 백업
     폴더는 자동 삭제.
2. **`RealEstateTransactionCollect`** — 1시간마다 반복, `collect_transactions.bat` →
   `collect_transaction_volume.py`.
   - `transaction_collect_progress` 체크포인트 테이블로 재개 가능한 배치 백필(시군구×유형×
     거래유형×월 조합, 최근 달→과거 순으로 처리). 한 번 실행에 최대 50분(`MAX_SECONDS_PER_RUN`)
     또는 5만 유닛(`MAX_UNITS_PER_RUN`)까지만 처리하고 멈춤 — 그래서 1시간 주기로 계속 이어서
     돌아야 전체가 채워짐.
   - `ThreadPoolExecutor(max_workers=3)` + 자체 레이트리미터(요청 간 0.35초, "PER_SECOND" 에러 나면
     backoff) — API가 초당 요청 제한이 있어서 워커 5개 이상 쓰면 429 에러가 급증함, 3이 적당.
   - 매매는 `해제여부`(취소) 컬럼 있는 행 제외하고 카운트, 평균가는 `거래금액` 평균. 전월세는
     `보증금액` 평균 + `월세금액>0`인 행만으로 `월세금액` 평균.
   - **버그 이력**: `PublicDataReader`가 HTTP 에러 응답도 "거래 0건"으로 조용히 처리해버려서 특정
     기간(2021-03~2023-06) 데이터가 전부 0으로 잘못 기록된 적 있음 — 반드시
     `_response_to_item_data`를 몽키패치해서 non-200 응답 시 예외를 던지도록 해야 함(그래야
     재시도/재수집이 됨).
   - 노트북이 잠자기 상태거나 메모리 부족으로 프로세스가 죽으면 다음 예약 시각까지 그냥
     멈춰있으므로, 오래 안 도는 것 같으면 수동으로 한 번 더 돌려주는 게 좋음
     (`.venv/Scripts/python.exe collect_transaction_volume.py`).

---

## 7. 디자인 시스템 (`theme.py`)

색상(참고 사이트 `https://hwshin0819.github.io/realtor/`에서 그대로 가져옴):
`GREEN #0E7A44`(강조/증가), `GREEN_DEEP #0A5A33`, `VERMILION #C64A2E`(감소/경고), `BLUE #2563EB`,
`INK #1B231E`(기본 텍스트), `CARD #FFFFFF`, `LINE #E2E6E1`(테두리), `MUTED #6B756E`(보조 텍스트),
`ROW_HOVER #F6F9F5`, `TABLE_LINE #EFF2EE`, `ACCENT_SOFT #E3F0EA`, `BG_PAGE #F8F9FA`.
폰트는 Pretendard Variable(CDN). 배경 `BG_PAGE`, 카드 배경 `CARD`, 본문 폭 1080px(계산기 페이지만
1440px로 확장).

핵심 재사용 CSS 컴포넌트(모든 페이지가 공유):
- **`.ov-stats`/`.ov-stat`**: KPI 카드 그리드(4열, 모바일 2열). `.ov-stat.open`=초록 값,
  `.ov-stat.close`=주홍 값, `.ov-stat.net .value.plus/.minus`=증감에 따라 초록/주홍.
- **`.ov-topline`**: 페이지 제목+부제목 한 줄.
- **`.ov-panel-title`/`.ov-panel-desc`**: 차트/패널 제목+설명 텍스트.
- **`.ov-table`**: 데이터 표 스타일(고정 첫 열, 가로 스크롤, 헤더 `.mo`/`.oc-o`(초록)/`.oc-c`(주홍),
  증감 셀 `.net-up`/`.net-down`). `.region-toggle`+`.chev`+`.district-cell`로 시/도 행 클릭 시 그
  아래로 시/군/구 행이 펼쳐지는 트리 테이블 패턴도 있음.
- 버튼: 기본은 아웃라인(테두리만), `primary` 타입만 초록 채움. 셀렉트박스 선택 옵션 = 초록 배경+
  흰 글자. `st.tabs`는 밑줄 스타일(선택 탭만 진초록+두꺼운 글씨, 초록 밑줄 인디케이터).
- 사이드바 라디오 메뉴는 체크박스/불릿 없이 그냥 텍스트만 굵게 바뀌는 방식으로 커스텀.

---

## 8. 앱 셸 (`app.py`) — 라우팅

- `st.set_page_config(page_title="이실장 사업팀 대시보드", layout="wide")` → `theme.inject()` →
  `auth.login_gate()`(로그인 안 되어 있으면 여기서 `st.stop()`).
- 사이드바: 사용자 이름/아이디/역할 표시 + 로그아웃 버튼 + 메뉴 라디오. **메뉴 항목은 권한과 무관하게
  전체 표시**, 권한 없는 항목만 회색(CSS `nth-child` 셀렉터로 개별 항목 스타일링). 관리자 전용 메뉴
  2개는 위쪽 메뉴들과 구분선으로 분리.
- 페이지 전환 시 스크롤을 맨 위로 올리는 트릭(`components.html`의 숨겨진 iframe에서
  `window.parent`로 접근해 강제 스크롤 — `st.sidebar.radio`는 탭과 달리 자동 스크롤이 안 되기 때문).
- 라우팅(문자열 상수 6개 + 1개는 admin 전용 하위탭 4개를 더 가짐):
  ```
  PAGE_INDUSTRY_TRENDS = "중개업 시장 동향"      → industry_trends.render()
  PAGE_TRANSACTIONS    = "실거래량 동향"          → transactions.render()
  PAGE_BROKERS         = "공인중개사 현황"        → (관리자면 5개 탭: 개요=brokers.render(),
                                                     웹훅 관리=webhooks.render(), 수집 대상=targets.render(),
                                                     수집테스트=collect_test.render(), 배치 스케줄=schedule.render())
                                                    (일반 유저는 brokers.render()만)
  PAGE_CALCULATOR      = "공헌이익 시뮬레이터"    → calculator.render()
  PAGE_ADMIN           = "관리자 계정 관리"       → admin.render() (admin만 사이드바에 노출)
  PAGE_ACCESS_LOG      = "시스템 접속 로그"       → access_log.render() (admin만)
  ```

---

## 9. 페이지별 상세 스펙

### 9.1 중개업 시장 동향 (`industry_trends.py` + 루트의 `industry_market_stats.py`)

정적 통계(통계청/국세청) 전용 페이지, 자체 수집 데이터 없음. `industry_market_stats.py`(별칭 `ims`)가
데이터 계층 — 통계청 연도별 표는 코드에 하드코딩된 리스트, TASIS는 `data/tasis_lifestyle_058.json`.

**탭 A "전국 시장 현황"**: KPI 4개(TAM=최근 3개년 평균 매출액[조원], 총매출/평균매출/사업체수 각각
"21년 고점 대비" 증감률) + 매출액(막대,드래그로 구간 선택 가능)·평균매출·영업이익 콤보차트(2020,
2025 결측) + 인력 구조(연령대 100% 스택바 + 성별 비중 라인차트, 국세청 개인사업자 기준) + 원본
수치 expander 표.

**탭 B "지역별 현황"**: 연도 선택 → 전국 지도(배경 choropleth + 평균연매출 크기의 버블
scattergeo, `data/korea_sido.geojson`) 클릭하면 그 시/도의 시/군/구로 드릴다운(세종처럼 하위
구분 없는 곳은 드릴다운 불가 안내) + 지역별 순위 가로바 차트(전국 평균 대비 점선) + 연도별 추이
(히트맵/라인차트 토글).
- **지도 클릭 버그 주의**: choropleth(배경)와 scattergeo(버블) 두 트레이스가 겹쳐 있어서, 클릭 시
  `event["selection"]["points"]`에 choropleth 쪽 포인트(customdata 없음)가 먼저 잡히면 클릭이
  무시되는 버그가 있었음 — **customdata가 있는 포인트를 찾아서 써야 함** (`points`를 순회하며 첫
  번째로 `customdata`가 있는 것을 clicked 값으로 사용).

### 9.2 실거래량 동향 (`transactions.py` + `real_estate_stats.py`)

국토부 실거래가(`transaction_monthly` 테이블) 기반. 지역(시도)/시작월/종료월 필터 + 빠른선택
(최근6개월/올해/최근12개월/전체). KPI 3장(기간 내 총 거래량/매매 거래량/전월세 거래량, 각각 비중%).
탭 A "거래량 추이": 매매(진한 블루)+전월세(연한 그레이) 누적 막대 + 매매 평균거래금액(코랄선,
보조축) + 실제 영업 중 사무소 수(검정 점선, 보조축2) 상관관계 차트, 월별/분기별 토글. 탭 B
"유형별 현황": 선택 기간 누적 기준 4개 유형(아파트/오피스텔/연립다세대/단독다가구) 비중 바+표.
당월(최신월)은 "실거래 신고기한 미전결"이라 확정월(전월)을 KPI 기준으로 쓰고 캡션으로 안내.

### 9.3 공인중개사 현황 (`brokers.py`)

가장 핵심 운영 페이지. 지역/시작월/종료월 필터(기본값 전체, 빠른선택: 최근6개월/올해/3개년/
5개년/전체) — **KPI 카드 4장은 필터를 따라가되, 필터가 기본값(전체 기간)이면 "이번달/당월" 기준으로
되돌아가는 특수 처리**(전체기간 누적을 "이달의 신규개업"이라고 보여주는 건 의미가 없어서):
1. 실제 영업 중 사무소(현재 스냅샷, 필터 무관 고정)
2. 이달의 신규 개업 / 기간 내 신규 개업 (필터가 전체면 "이달", 좁히면 "기간 내"로 라벨도 바뀜)
3. 당월 폐업 / 기간 내 폐업 (위와 동일 로직)
4. 당월 순증감 / 기간 내 순증감 (개업-폐업, 양수 초록/음수 빨강)

3개 탭:
- **그래프 추이**: 개업(초록)/폐업(주홍) 막대 + 순증감(파랑선, 왼쪽 축) + 실제 영업 중 사무소 수
  (검정 점선, 오른쪽 축) 를 **하나의 차트로 합침** (원래는 차트 2개였는데 사용자 요청으로 병합).
- **지역별 상세**: 시/도 행 클릭하면 시/군/구가 펼쳐지는 트리 테이블(전국 선택 시) 또는 특정
  시도의 시군구 표, 엑셀 다운로드.
- **B2B 신규 영업 타겟**: 이번 달 등록일자인 사무소 리스트(상호명/법정동/등록일자), 엑셀 다운로드
  — 영업팀이 신규 개업 중개사무소에 연락하기 위한 리드 리스트.

관리자로 로그인하면 이 페이지 위에 4개 탭이 더 붙음(전부 `data_store.py` JSON 기반 UI, 실제
스케줄러 아님 — 진짜 자동화는 Windows 작업 스케줄러): 웹훅 관리(이벤트별 URL 등록), 수집 대상
(브이월드 조회 대상 지역 관리), 수집테스트(랜덤 목데이터로 수집 결과 미리보기), 배치 스케줄
(주기 설정 UI, 실제 실행기는 없음).

### 9.4 공헌이익 시뮬레이터 (`calculator.py`)

외부 영업팀용 "제휴 룸 계산기"를 이 대시보드 스타일로 재구현. 4개 지역 × 2개 계약기간(6개월/1년)
× 3개 상품등급(Lite/Basic/Mega) = 24개 가격 조합에 대해, 할인/유치수수료/관리수수료/무료체험권을
사용자가 조정하면 신규·재계약 각각의 **공헌이익·공헌이익률**을 계산하고, 상품별 기준선(floor rate)
대비 통과/실패를 판정. PG수수료는 고정 2.508%(부가세 포함). 공식과 기준선은 표 원본 가격의
유치수수료/관리수수료율/쿠폰비용으로 고정 계산(할인해도 기준선 자체는 안 바뀜). 대량의 raw HTML
테이블(before→after 취소선 비교, pass/fail 알약 배지)로 렌더링.

### 9.5 관리자 계정 관리 (`admin.py`, admin 전용)

계정 목록 표 + 계정 생성(아이디/이름/초기비번/역할/접근 메뉴 다중선택) + 접근 권한 변경 +
비밀번호 재설정(관리자가 새 값 직접 입력, 기존 비번 확인 불필요) + 계정 삭제(자기 자신·마지막
admin은 삭제 불가, 체크박스로 확인).

### 9.6 시스템 접속 로그 (`access_log.py`, admin 전용)

`data_store.load_access_log()`를 표로, 아이디/결과/IP 3개 필터.

---

## 10. 알아두면 좋은 환경적 특이사항 (재구성 시에도 반복될 수 있음)

- **Windows 배시 도구에서 한글이 깨져 보이는 문제**: 실제 데이터/코드는 정상(UTF-8)인데 특정 터미널
  환경에서 한글이 mojibake로 보일 뿐이라, 파일에 써서 Read 도구로 다시 확인하면 정상적으로 보임 —
  당황하지 말고 파일 경유로 확인할 것.
- **국토부 API가 초당 요청 제한이 엄격**해서 워커를 늘리면 오히려 429 에러가 쌓여 느려짐 — 3개
  정도가 적당했음.
- **이 PC가 메모리 부족(15.5GB 중 여유 2~3GB)** 상태가 잦아서 Streamlit 서버나 백필 프로세스가
  예고 없이 죽는 일이 자주 있었음 — 죽으면 그냥 다시 켜주면 됨, 근본 해결은 다른 프로그램 정리.
- **노트북 잠자기 때문에 새벽 예약 작업이 놓치는 경우**가 있었음 — Windows가 깨어나면 "따라잡기"로
  뒤늦게 실행되긴 하지만, 그사이 몇 시간 손해를 봄. 오래 멈춰있는 것 같으면 수동으로 한 번 더
  돌려주는 게 나음.
- **같은 프로젝트를 동시에 다른 세션(다른 관리자)이 건드릴 수 있음** — `data/users.json` 같은 파일을
  건드리기 전엔 항상 다시 읽어서 최신 상태를 확인하고, 예상 못한 변경(계정이 늘거나 줄어듦)이
  보이면 내가 지운 게 아니라는 걸 먼저 확인한 뒤 사용자에게 물어볼 것.
- **엑셀 파일이 사람이 열어놓은 상태면 저장이 실패**할 수 있음 — collector.py는 이 실패를 무시하고
  넘어가도록 이미 설계돼 있으니 이 패턴을 재구현 시에도 유지할 것.

