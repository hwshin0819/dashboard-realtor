# -*- coding: utf-8 -*-
"""'부동산중개업 시장 동향' 메뉴용 고정 데이터.

두 출처를 담는다.
- NATIONAL_TREND: 통계청(국가데이터처) 서비스업조사보고서, 'L 부동산업 > 1.산업별 총괄' 표에서
  산업코드 68221(부동산 중개 및 대리업) 한 줄만 뽑은 전국 연도별 수치(2017~2024, 2020 제외).
  0/5년차(2015, 2020, 2025)는 서비스업조사 대신 경제총조사로 대체되어 이 표 자체가 없다.
  API가 없어 매년 수동 갱신 필요.
- data/tasis_lifestyle_058.json: TASIS(국세통계포털) '통계로 보는 생활업종 > 부동산중개업'.
  화면상으론 연도 선택이 없지만, 내부적으로 호출하는 wqAction.do?actionId=ATWEPFLA001R03
  API가 비공개로 존재해서(세션·로그인 불필요) 전국·시/도·전국 229개 시/군/구를
  2021~2025년(YR 파라미터, 이 범위 밖은 서버가 에러 응답) 전부 직접 받았다.
  YR=년은 '사업자수는 그 해 말 기준, 평균매출은 그 전해 귀속소득'을 의미한다
  (예: YR=2025 → 사업자수 2025년 말, 매출 2024년 귀속).
"""

import json

# 통계청 서비스업조사보고서, 'L 부동산업'>'1. 산업별 총괄' 표의 68221(부동산 중개 및 대리업) 행.
# 단위: 사업체수(개), 종사자수(명), 그 외 전부 백만원.
NATIONAL_TREND = [
    {"연도": 2017, "사업체수": 94621, "종사자수": 149821, "매출액": 9045569, "영업비용": 8083926, "인건비": 603685, "임차료": 252781, "기타경비": 7227459, "급여총액": 513265},
    {"연도": 2018, "사업체수": 99299, "종사자수": 153883, "매출액": 9829678, "영업비용": 8866059, "인건비": 796805, "임차료": 253387, "기타경비": 7815867, "급여총액": 629328},
    {"연도": 2019, "사업체수": 100088, "종사자수": 156371, "매출액": 8361304, "영업비용": 7489918, "인건비": 751734, "임차료": 241322, "기타경비": 6496862, "급여총액": 577556},
    {"연도": 2021, "사업체수": 120172, "종사자수": 161191, "매출액": 16544728, "영업비용": 15129221, "인건비": 1314455, "임차료": 570138, "기타경비": 13244628, "급여총액": 1086844},
    {"연도": 2022, "사업체수": 122135, "종사자수": 162670, "매출액": 13631412, "영업비용": 13747562, "인건비": 1003916, "임차료": 430362, "기타경비": 12313283, "급여총액": 797951},
    {"연도": 2023, "사업체수": 115105, "종사자수": 146114, "매출액": 11506937, "영업비용": 11266401, "인건비": 941745, "임차료": 453054, "기타경비": 9871603, "급여총액": 719574},
    {"연도": 2024, "사업체수": 108526, "종사자수": 131436, "매출액": 7614267, "영업비용": 7290183, "인건비": 1161060, "임차료": 420170, "기타경비": 5708953, "급여총액": 1009696},
]

# geojson(data/korea_sido.geojson)의 properties.code 와 맞춘 지역 코드.
REGION_CODE = {
    "서울": "11", "부산": "21", "대구": "22", "인천": "23", "광주": "24",
    "대전": "25", "울산": "26", "세종": "29", "경기": "31", "강원": "32",
    "충북": "33", "충남": "34", "전북": "35", "전남": "36", "경북": "37",
    "경남": "38", "제주": "39",
}
REGION_ORDER = list(REGION_CODE.keys())


def national_trend() -> list:
    """연도 오름차순. 매출액/영업비용 등은 백만원, 평균매출(만원)을 추가로 계산해 붙여 돌려준다."""
    out = []
    for row in NATIONAL_TREND:
        r = dict(row)
        r["평균매출_만원"] = round(r["매출액"] * 1_000_000 / r["사업체수"] / 10000)
        r["영업이익_만원"] = round((r["매출액"] - r["영업비용"]) * 1_000_000 / r["사업체수"] / 10000)
        out.append(r)
    return sorted(out, key=lambda r: r["연도"])


def geojson_path() -> str:
    return "data/korea_sido.geojson"


_TASIS_JSON_PATH = "data/tasis_lifestyle_058.json"
_tasis_cache = None


def _load_tasis() -> dict:
    global _tasis_cache
    if _tasis_cache is None:
        with open(_TASIS_JSON_PATH, encoding="utf-8") as f:
            _tasis_cache = json.load(f)
    return _tasis_cache


def tasis_years() -> list:
    """조회 가능한 연도(YR) 목록, 오름차순. 예: ['2021','2022','2023','2024','2025']."""
    return sorted(_load_tasis()["national"].keys())


def tasis_national(year: str) -> dict:
    return dict(_load_tasis()["national"][year])


def tasis_sido_snapshot(year: str, include_national: bool = False) -> list:
    """해당 연도의 시/도별 스냅샷. REGION_ORDER 순서, 평균연매출 내림차순으로 정렬해 돌려준다."""
    data = _load_tasis()["sido"]
    rows = [{"지역": name, **data[name][year]} for name in REGION_ORDER if year in data.get(name, {})]
    rows.sort(key=lambda r: -(r["평균연매출"] or 0))
    if include_national:
        rows = [{"지역": "전국", **tasis_national(year)}] + rows
    return rows


def tasis_has_district(sido_short: str) -> bool:
    """시/군/구가 2개 이상 있어야 드릴다운 의미가 있다(세종은 자기 자신 1개뿐이라 제외)."""
    return len(_load_tasis()["district"].get(sido_short, {})) >= 2


def tasis_district_snapshot(sido_short: str, year: str) -> list:
    """해당 시/도의 연도별 시/군/구 스냅샷(위경도 포함), 평균연매출 내림차순."""
    tasis = _load_tasis()
    districts = tasis["district"].get(sido_short, {})
    meta = tasis["district_meta"].get(sido_short, {})
    rows = []
    for name, by_year in districts.items():
        if year not in by_year or name not in meta:
            continue
        rows.append({"시군구": name, **by_year[year], **meta[name]})
    rows.sort(key=lambda r: -(r["평균연매출"] or 0))
    return rows


def tasis_sido_trend(include_national: bool = True) -> dict:
    """{지역명: {연도: 평균연매출}} 형태로, 시/도(+전국) 전체의 연도별 추이를 한 번에 돌려준다."""
    tasis = _load_tasis()
    years = tasis_years()
    out = {}
    if include_national:
        out["전국"] = {y: tasis["national"][y]["평균연매출"] for y in years}
    for name in REGION_ORDER:
        by_year = tasis["sido"].get(name, {})
        out[name] = {y: by_year[y]["평균연매출"] for y in years if y in by_year}
    return out


def tasis_district_trend(sido_short: str) -> dict:
    """{시군구명: {연도: 평균연매출}} 형태로, 해당 시/도 시군구 전체의 연도별 추이를 한 번에 돌려준다."""
    tasis = _load_tasis()
    years = tasis_years()
    districts = tasis["district"].get(sido_short, {})
    return {
        name: {y: by_year[y]["평균연매출"] for y in years if y in by_year}
        for name, by_year in districts.items()
    }


def tasis_district_bounds(sido_short: str, pad: float = 0.06) -> dict:
    """해당 시/도 시군구 중심좌표들을 감싸는 범위(+여백). 지도 확대(zoom)용."""
    meta = _load_tasis()["district_meta"].get(sido_short, {})
    if not meta:
        return {"lat_range": [33, 39], "lon_range": [124.5, 131]}
    lats = [m["lat"] for m in meta.values()]
    lons = [m["lon"] for m in meta.values()]
    return {
        "lat_range": [min(lats) - pad, max(lats) + pad],
        "lon_range": [min(lons) - pad, max(lons) + pad],
    }


# TASIS '통계로 보는 생활업종 > 부동산중개업' 화면의 성별/연령대별 종사자 비율(%), 전국 단위.
# 시/도·시/군/구별 분해는 API가 제공하지 않아 전국 수치만 있다.
TASIS_GENDER_TREND = {
    2021: {"남자": 54.4, "여자": 45.6},
    2022: {"남자": 54.0, "여자": 45.9},
    2023: {"남자": 53.5, "여자": 46.5},
    2024: {"남자": 52.8, "여자": 47.2},
    2025: {"남자": 52.3, "여자": 47.7},
}

AGE_BRACKET_ORDER = ["30세미만", "30대", "40대", "50대", "60대", "70세이상"]

TASIS_AGE_TREND = {
    2021: {"30세미만": 1.6, "30대": 7.9, "40대": 22.2, "50대": 39.4, "60대": 23.5, "70세이상": 5.4},
    2022: {"30세미만": 1.6, "30대": 7.8, "40대": 21.1, "50대": 38.8, "60대": 24.8, "70세이상": 5.9},
    2023: {"30세미만": 1.3, "30대": 7.5, "40대": 19.7, "50대": 38.9, "60대": 26.2, "70세이상": 6.4},
    2024: {"30세미만": 1.1, "30대": 7.0, "40대": 18.4, "50대": 38.4, "60대": 27.8, "70세이상": 7.3},
    2025: {"30세미만": 0.9, "30대": 6.7, "40대": 17.4, "50대": 37.1, "60대": 29.5, "70세이상": 8.4},
}


def tasis_gender_trend() -> dict:
    """{연도: {'남자': %, '여자': %}}, 연도 오름차순."""
    return dict(sorted(TASIS_GENDER_TREND.items()))


def tasis_age_trend() -> dict:
    """{연도: {연령대: %}}, 연도 오름차순. 연령대 순서는 AGE_BRACKET_ORDER."""
    return dict(sorted(TASIS_AGE_TREND.items()))


# 국토부(한국공인중개사협회 집계) 개업 공인중개사 등록 현황. 대시보드 내 비교용 참고치라 수동 갱신.
OFFICIAL_BROKER_COUNT = {"기준": "2024년", "값": 109979}


def tam_band() -> dict:
    """KOSIS 총매출액 기준 TAM 추정. 최근 3개년 평균(중심값)과 최근 4개년 범위(변동성 참고용)을 조원 단위로 돌려준다.
    표본조사 특성상 단일 연도 값은 출렁임이 커서, 대표값은 3개년 평균을 쓰고 범위를 같이 보여준다."""
    trend = national_trend()
    last3 = trend[-3:]
    last4 = trend[-4:]
    return {
        "avg3_조원": sum(r["매출액"] for r in last3) / 3 / 1_000_000,
        "years3": [r["연도"] for r in last3],
        "lo_조원": min(r["매출액"] for r in last4) / 1_000_000,
        "hi_조원": max(r["매출액"] for r in last4) / 1_000_000,
        "years4": [r["연도"] for r in last4],
    }


def kosis_tasis_compare() -> list:
    """KOSIS 연도별 수치와, 그 해에 귀속된 소득을 담은 TASIS(YR=연도+1) 전국 수치를 나란히 비교해 돌려준다.
    TASIS는 'YR년 = 그 전해 귀속소득'이라, 같은 소득연도를 보려면 TASIS YR을 한 해 밀어서 맞춰야 한다.
    TASIS는 2021년 귀속(YR=2022)부터만 있어 그 이전 KOSIS 연도는 tasis_* 값이 None으로 채워진다."""
    tasis = _load_tasis()["national"]
    out = []
    for row in national_trend():
        yr = row["연도"]
        t = tasis.get(str(yr + 1))
        entry = {
            "연도": yr,
            "kosis_사업체수": row["사업체수"],
            "kosis_평균매출_만원": row["평균매출_만원"],
            "kosis_영업이익_만원": row["영업이익_만원"],
            "kosis_총매출_조원": row["매출액"] / 1_000_000,
            "tasis_사업자수": t["사업자수"] if t else None,
            "tasis_평균매출_만원": t["평균연매출"] if t else None,
            "tasis_총매출_조원": (t["평균연매출"] * t["사업자수"] / 100_000_000) if t else None,
        }
        out.append(entry)
    return out
