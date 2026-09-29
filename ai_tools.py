# -*- coding: utf-8 -*-
"""AI 에이전트가 Gemini function-calling으로 부르는 도구 함수들.
실거래량 동향/CP 현황/공인중개사 개폐업 현황/중개업 시장 동향, 4개 도메인을 각각
real_estate_stats.py / cp_stats.py / real_stats.py / industry_market_stats.py를 얇게 감싸서 노출한다.
함수 시그니처의 타입힌트·docstring이 그대로 Gemini에 전달되는 함수 스펙이 되므로,
파라미터 설명을 사람이 아니라 모델이 읽는다는 전제로 정확하게 적는다."""
import region_utils as ru
import real_estate_stats as res
import cp_stats as cs
import real_stats
import industry_market_stats as ims

REGION_GROUPS = {"수도권": ru.METRO_SIDOS, "지방": ru.NON_METRO_SIDOS}
VALID_REGIONS = ["전국", "수도권", "지방"] + ru.REGION_ORDER[1:]
PROPERTY_TYPES = ["전체"] + res.PROPERTY_TYPES
TRADE_TYPES = ["전체"] + res.TRADE_TYPES


def _resolve_region(region: str):
    """region 문자열 -> load_monthly_series_for_sidos에 넘길 시/도 목록(None이면 전국)."""
    if region not in VALID_REGIONS:
        raise ValueError(f"'{region}'은 알 수 없는 지역입니다. 사용 가능한 값: {VALID_REGIONS}")
    if region == "전국":
        return None
    if region in REGION_GROUPS:
        return REGION_GROUPS[region]
    return [region]


def get_transaction_trend(region: str, property_type: str, trade_type: str,
                           start_month: str, end_month: str) -> dict:
    """국토교통부 실거래가 기준, 월별 부동산 거래량·평균 가격 추이를 조회한다.

    Args:
        region: '전국', '수도권'(서울+경기+인천), '지방'(수도권 제외), 또는 시/도 이름
            (서울, 경기, 인천, 부산, 대구, 광주, 대전, 울산, 세종, 강원, 충북, 충남,
            전북, 전남, 경북, 경남, 제주) 중 하나.
        property_type: '전체', '아파트', '오피스텔', '연립다세대', '단독다가구' 중 하나.
        trade_type: '전체', '매매', '전월세' 중 하나.
        start_month: 조회 시작 월, 'YYYY-MM' 형식 (예: '2024-01').
        end_month: 조회 종료 월, 'YYYY-MM' 형식. start_month보다 같거나 커야 한다.

    Returns:
        총 거래건수, 매매면 평균 거래가(만원), 전월세면 평균 보증금·평균 월세(만원),
        그리고 월별 세부 내역이 담긴 dict.
    """
    sidos = _resolve_region(region)
    series = res.load_monthly_series_for_sidos(sidos, property_type, trade_type)
    rows = [r for r in series if start_month <= r["월"] <= end_month]
    if not rows:
        return {"error": "해당 조건(지역/유형/기간)에 데이터가 없습니다."}

    total_count = sum(r["건수"] for r in rows)
    price_n = [(r["평균매매가"], r["건수"]) for r in rows if r["평균매매가"] is not None]
    deposit_n = [(r["평균보증금"], r["건수"]) for r in rows if r["평균보증금"] is not None]
    rent_n = [(r["평균월세"], r["건수"]) for r in rows if r["평균월세"] is not None]

    def _wavg(pairs):
        n = sum(c for _, c in pairs)
        return round(sum(v * c for v, c in pairs) / n) if n else None

    return {
        "region": region, "property_type": property_type, "trade_type": trade_type,
        "start_month": start_month, "end_month": end_month,
        "총거래건수": total_count,
        "평균매매가_만원": _wavg(price_n),
        "평균보증금_만원": _wavg(deposit_n),
        "평균월세_만원": _wavg(rent_n),
        "월별": rows,
    }


def get_jeonse_wolse_summary(region: str, start_month: str, end_month: str) -> dict:
    """전세/월세를 나눠서 평균 보증금과 평균 월세를 조회한다(전월세 거래만 대상).
    전세 보증금(수억원대)과 월세 보증금(수천만원대)은 성격이 달라 따로 낸다.

    Args:
        region: get_transaction_trend와 같은 규칙 ('전국'/'수도권'/'지방'/시·도 이름).
        start_month: 조회 시작 월, 'YYYY-MM' 형식.
        end_month: 조회 종료 월, 'YYYY-MM' 형식.

    Returns:
        전세평균보증금, 월세평균보증금, 평균월세(모두 만원 단위)와 각각의 건수가 담긴 dict.
    """
    sidos = _resolve_region(region)
    if sidos is None:
        return res.jeonse_wolse_summary(start_month, end_month, "전국")
    if len(sidos) == 1:
        return res.jeonse_wolse_summary(start_month, end_month, sidos[0])
    return res.jeonse_wolse_summary_for_sidos(start_month, end_month, sidos)


# ── CP 현황 (cp_stats.py) ─────────────────────────────────────────────────────
# CP사 이름은 원본 데이터에서 매달 동적으로 뽑히는 값이라 고정 목록으로 못 박을 수 없다.
# 그래서 다른 도메인과 달리 VALID_* 상수 대신 list_cp_reference_data() 도구를 하나 더 두고,
# 시스템 프롬프트에서 "정확한 CP사명·월을 모르면 이걸 먼저 불러라"라고 안내한다.

def _cp_load() -> dict:
    D = cs.load_default()
    if D is None:
        raise ValueError("CP 현황 원본 데이터가 아직 등록되어 있지 않습니다.")
    return D


def _cp_month_index(D: dict, month: str) -> int:
    if month in D["months"]:
        return D["months"].index(month)
    if month in D["labels"]:
        return D["labels"].index(month)
    raise ValueError(f"'{month}'은 알 수 없는 월입니다. 사용 가능한 값(YYYY-MM): {D['months']}")


def _cp_resolve(D: dict, cp: str) -> str:
    valid = [cs.PROPTIER] + D["cps"]
    if cp not in valid:
        raise ValueError(
            f"'{cp}'는 알 수 없는 CP사입니다. list_cp_reference_data로 정확한 이름을 먼저 확인해라. "
            f"사용 가능한 값: {valid}"
        )
    return cp


def list_cp_reference_data() -> dict:
    """CP 현황 도구(get_cp_method_mix 등)를 부르기 전에, 그 시점 기준 정확한 CP사 이름·월·시도·
    검증방식 목록이 필요하면 이 함수를 먼저 호출한다. CP사 이름은 원본 데이터가 갱신될 때마다
    바뀔 수 있어 고정된 목록이 없다.

    Returns:
        cp_companies(CP사명 목록, '프롭티어'는 이실장+매경 합산 가상 회사), months(YYYY-MM 목록),
        month_labels(월 표시 라벨, 예 '7월'), sidos(시/도 17개), verification_methods(실사용 중인
        검증방식), property_groups(매물유형 3종), zones(권역 2종)가 담긴 dict.
    """
    D = _cp_load()
    return {
        "cp_companies": [cs.PROPTIER] + D["cps"],
        "months": D["months"],
        "month_labels": D["labels"],
        "sidos": D["sidos"],
        "verification_methods": D["methods_active"],
        "property_groups": D["groups"],
        "zones": D["zones"],
    }


def get_cp_method_mix(cp: str, month: str, region: str = "전체", include_hangong: bool = False) -> dict:
    """검증방식(현장확인/홍보확인서 등)별 매물수와 구성비(%)를 조회한다.

    Args:
        cp: '시장전체'(전체 CP사 합산)를 주거나, list_cp_reference_data가 돌려준 CP사명
            (또는 '프롭티어')을 정확히 그대로 준다.
        month: list_cp_reference_data의 months 또는 month_labels 중 하나 ('YYYY-MM' 또는 '7월' 형식).
        region: '전체'(전국), '수도권', '지방', 또는 시/도 이름 중 하나. 기본값 '전체'.
        include_hangong: cp='시장전체'일 때만 의미 있음. 회원사가 아닌 '한공협'을 시장 합계에
            포함할지 여부(기본 False = 제외).

    Returns:
        cp, month, region, 총매물수와, 검증방식별 매물수·구성비(%)를 매물수 내림차순으로 담은 dict.
    """
    D = _cp_load()
    i = _cp_month_index(D, month)
    if region not in cs.region_options(D):
        raise ValueError(f"'{region}'은 알 수 없는 지역입니다. 사용 가능한 값: {cs.region_options(D)}")
    if cp == "시장전체":
        counts = cs.method_market(D, i, include_hangong, region)
    else:
        cp = _cp_resolve(D, cp)
        counts = cs.method_vec(D, cp, i, region)
    total = sum(v for v in counts if v is not None)
    rows = [
        {"검증방식": m, "매물수": v, "구성비_pct": round(v / total * 100, 1) if (v is not None and total) else None}
        for m, v in zip(cs.METHODS, counts)
    ]
    rows.sort(key=lambda r: (r["매물수"] is None, -(r["매물수"] or 0)))
    return {"cp": cp, "month": month, "region": region, "총매물수": total, "검증방식별": rows}


def get_cp_market_share(cp: str, month: str, include_hangong: bool = False) -> dict:
    """특정 CP사의 시장 점유율(매물수 기준, 회원수 기준)을 조회한다.

    Args:
        cp: list_cp_reference_data가 돌려준 CP사명(또는 '프롭티어'). '시장전체'는 여기선 의미가
            없으므로 줄 수 없다.
        month: list_cp_reference_data의 months 또는 month_labels 중 하나.
        include_hangong: 분모(시장 전체)에 회원사가 아닌 '한공협'을 포함할지 여부(기본 False).

    Returns:
        해당 cp의 매물수·회원수와, 시장 전체 대비 매물점유율(%)·회원점유율(%)이 담긴 dict.
    """
    D = _cp_load()
    i = _cp_month_index(D, month)
    cp = _cp_resolve(D, cp)
    listing_share = cs.share_series(D, cp, "l", include_hangong)[i]
    member_share = cs.share_series(D, cp, "m", include_hangong)[i]
    return {
        "cp": cp, "month": month,
        "매물수": D["d"][cp]["l"][i], "회원수": D["d"][cp]["m"][i],
        "매물점유율_pct": round(listing_share, 1) if listing_share is not None else None,
        "회원점유율_pct": round(member_share, 1) if member_share is not None else None,
    }


def get_cp_composition_breakdown(cp: str, month: str, dimension: str, include_hangong: bool = False) -> dict:
    """CP사(또는 시장전체)의 매물이 시/도·매물유형·권역 중 하나의 기준으로 어떻게 나뉘는지(구성비교) 조회한다.

    Args:
        cp: '시장전체'(전체 CP사 합산)를 주거나, list_cp_reference_data가 돌려준 CP사명(또는 '프롭티어').
        month: list_cp_reference_data의 months 또는 month_labels 중 하나.
        dimension: '시도'(17개 시/도별), '매물유형'(공동주택/비공동주택/비공동비주택), '권역'(수도권/지방) 중 하나.
        include_hangong: cp='시장전체'일 때만 의미 있음. '한공협'을 포함할지 여부(기본 False).

    Returns:
        cp, month, dimension, 총매물수와, 구분별 매물수·구성비(%)를 매물수 내림차순으로 담은 dict.
    """
    D = _cp_load()
    i = _cp_month_index(D, month)
    dim_map = {"시도": ("sl", D["sidos"]), "매물유형": ("gl", D["groups"]), "권역": ("zl", D["zones"])}
    if dimension not in dim_map:
        raise ValueError(f"'{dimension}'은 알 수 없는 구분입니다. 사용 가능한 값: {list(dim_map)}")
    key, labels = dim_map[dimension]
    if cp == "시장전체":
        values = cs.market_vec(D, key, i, include_hangong, len(labels))
    else:
        cp = _cp_resolve(D, cp)
        values = D["d"][cp][key][i] or [None] * len(labels)
    total = sum(v for v in values if v is not None)
    rows = [
        {"구분": lab, "매물수": v, "구성비_pct": round(v / total * 100, 1) if (v is not None and total) else None}
        for lab, v in zip(labels, values)
    ]
    rows.sort(key=lambda r: (r["매물수"] is None, -(r["매물수"] or 0)))
    return {"cp": cp, "month": month, "dimension": dimension, "총매물수": total, "구성": rows}


# ── 공인중개사 개폐업 현황 (real_stats.py) ────────────────────────────────────

def _month_range(start_month: str, end_month: str) -> list:
    y1, m1 = (int(x) for x in start_month.split("-"))
    y2, m2 = (int(x) for x in end_month.split("-"))
    out = []
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def get_office_open_close_stats(region: str, start_month: str, end_month: str) -> dict:
    """공인중개사무소의 월별 개업·폐업·영업중 건수(개폐업 현황)를 지역·기간별로 조회한다.

    Args:
        region: '전국' 또는 시/도 이름(서울, 경기, 인천, 부산, 대구, 광주, 대전, 울산, 세종,
            강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주) 중 하나.
        start_month: 조회 시작 월, 'YYYY-MM' 형식.
        end_month: 조회 종료 월, 'YYYY-MM' 형식.

    Returns:
        기간 합계 총개업·총폐업·순증감, 기간 내 가장 최근 실측 영업중 건수, 월별 세부 내역이
        담긴 dict.
    """
    if region != "전국" and region not in ru.FULL_NAME:
        raise ValueError(f"'{region}'은 알 수 없는 지역입니다. 사용 가능한 값: ['전국'] + {ru.REGION_ORDER[1:]}")
    target = "전국" if region == "전국" else ru.FULL_NAME[region]
    rows = [r for r in real_stats.load_region_monthly_stats()
            if r["지역"] == target and start_month <= r["월"] <= end_month]
    if not rows:
        return {"error": "해당 조건(지역/기간)에 데이터가 없습니다."}
    rows.sort(key=lambda r: r["월"])
    total_open = sum(r["개업"] or 0 for r in rows)
    total_close = sum(r["폐업"] or 0 for r in rows)
    latest_active = next((r["영업중"] for r in reversed(rows) if r["영업중"] is not None), None)
    return {
        "region": region, "start_month": start_month, "end_month": end_month,
        "총개업": total_open, "총폐업": total_close, "순증감": total_open - total_close,
        "최근영업중": latest_active, "월별": rows,
    }


def get_district_open_close_ranking(start_month: str, end_month: str, top_n: int = 5) -> dict:
    """시/군/구 단위로 개업·폐업·순증감이 많은 지역 순위를 조회한다. 시/군/구 데이터는
    자체 수집을 시작한 2026-09월 수집분부터만 존재하므로, 그 이전 기간은 결과가 비어 있을 수 있다.

    Args:
        start_month: 조회 시작 월, 'YYYY-MM' 형식.
        end_month: 조회 종료 월, 'YYYY-MM' 형식.
        top_n: 순위를 몇 개씩 보여줄지(기본 5).

    Returns:
        순증가_상위, 순감소_상위(각각 {"지역","개업","폐업","순증감"} 목록)가 담긴 dict.
    """
    months = _month_range(start_month, end_month)
    rows = real_stats.top_bottom_districts(months)
    if not rows:
        return {"error": "해당 기간에 시/군/구 데이터가 없습니다(2026-09월 이후 수집분부터만 존재)."}
    by_net_desc = sorted(rows, key=lambda r: -r["순증감"])
    by_net_asc = sorted(rows, key=lambda r: r["순증감"])
    return {
        "start_month": start_month, "end_month": end_month,
        "순증가_상위": by_net_desc[:top_n], "순감소_상위": by_net_asc[:top_n],
    }


def get_current_office_status_snapshot() -> dict:
    """가장 최근 수집 스냅샷 기준, 전국 공인중개사무소의 상태별(영업중/폐업 등) 건수와
    이번 달 신규 개업 건수를 조회한다. 파라미터가 없다.

    Returns:
        기준일자, 상태별_건수(상태명 -> 건수), 휴업_휴업연장_업무정지(각 건수), 이번달_신규개업_건수가
        담긴 dict.
    """
    return {
        "기준일자": real_stats.load_latest_snapshot_date(),
        "상태별_건수": real_stats.load_office_status_counts(),
        "휴업_휴업연장_업무정지": real_stats.load_latest_status_breakdown(),
        "이번달_신규개업_건수": len(real_stats.load_new_offices_this_month()),
    }


# ── 중개업 시장 동향 (industry_market_stats.py) ───────────────────────────────

def get_industry_national_trend(start_year: int, end_year: int) -> dict:
    """통계청 서비스업조사(KOSIS) 기준, 부동산 중개업 전국 연도별 사업체수·매출액·평균매출·
    영업이익 추이를 조회한다. 2020년은 경제총조사로 대체되어 이 표에 없다.

    Args:
        start_year: 조회 시작 연도. 데이터가 있는 연도: 2017,2018,2019,2021,2022,2023,2024.
        end_year: 조회 종료 연도.

    Returns:
        연도별 사업체수/종사자수/매출액(백만원)/평균매출_만원/영업이익_만원 등이 담긴 목록을 포함한 dict.
    """
    rows = [r for r in ims.national_trend() if start_year <= r["연도"] <= end_year]
    if not rows:
        return {"error": "해당 기간에 데이터가 없습니다. 데이터가 있는 연도: 2017,2018,2019,2021,2022,2023,2024."}
    return {"start_year": start_year, "end_year": end_year, "연도별": rows}


def get_industry_tam_estimate() -> dict:
    """부동산 중개업 전체 시장 규모(TAM) 추정치를 조회한다. 표본조사 특성상 단일 연도 값은
    출렁임이 커서, 최근 3개년 평균을 대표값(중심값)으로 쓰고 최근 4개년 범위를 변동성 참고용으로
    같이 준다. 파라미터가 없다.

    Returns:
        avg3_조원(3개년 평균, 대표값), years3, lo_조원/hi_조원(4개년 범위), years4가 담긴 dict.
    """
    return ims.tam_band()


def get_tasis_snapshot(region: str, year: str) -> dict:
    """국세통계포털(TASIS) 기준, 해당 연도·지역의 평균연매출·사업자수·전년대비 증감·평균존속연수
    스냅샷을 조회한다. TASIS 연도는 'YR년 = 그 전해 귀속소득' 기준이다(예: 2025년 값은 2024년 귀속소득).

    Args:
        region: '전국' 또는 시/도 이름(서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종, 경기, 강원,
            충북, 충남, 전북, 전남, 경북, 경남, 제주) 중 하나.
        year: 조회 연도. '2021'~'2025' 중 하나(문자열).

    Returns:
        region, year, 평균연매출(만원), 매출전년대비(%, 2021년은 None), 사업자수,
        사업자수전년대비(%, 2021년은 None), 평균존속연수(예 '6년 6개월')가 담긴 dict.
    """
    years = ims.tasis_years()
    if year not in years:
        raise ValueError(f"'{year}'은 알 수 없는 연도입니다. 사용 가능한 값: {years}")
    if region == "전국":
        data = ims.tasis_national(year)
    else:
        if region not in ims.REGION_ORDER:
            raise ValueError(f"'{region}'은 알 수 없는 지역입니다. 사용 가능한 값: {['전국'] + ims.REGION_ORDER}")
        rows = ims.tasis_sido_snapshot(year, include_national=False)
        match = next((r for r in rows if r["지역"] == region), None)
        if match is None:
            return {"error": f"'{region}'의 {year}년 데이터가 없습니다."}
        data = {k: v for k, v in match.items() if k != "지역"}
    return {"region": region, "year": year, **data}


def get_tasis_trend(region: str) -> dict:
    """국세통계포털(TASIS) 기준, 지역별 평균연매출(만원)의 연도별(2021~2025) 추이를 조회한다.

    Args:
        region: '전국' 또는 시/도 이름(get_tasis_snapshot과 같은 규칙).

    Returns:
        region과, {연도: 평균연매출_만원} 형태의 연도별 추이가 담긴 dict.
    """
    if region != "전국" and region not in ims.REGION_ORDER:
        raise ValueError(f"'{region}'은 알 수 없는 지역입니다. 사용 가능한 값: {['전국'] + ims.REGION_ORDER}")
    trend_map = ims.tasis_sido_trend(include_national=True)
    return {"region": region, "연도별_평균연매출_만원": trend_map.get(region, {})}


def get_industry_demographics_trend() -> dict:
    """부동산 중개업 종사자의 성별·연령대별 비중 연도별(2021~2025) 추이를 조회한다. 전국 단위로만
    존재하며 지역별 분해는 불가능하다. 파라미터가 없다.

    Returns:
        성별_비중_추이_pct({연도: {'남자':%, '여자':%}}), 연령대_비중_추이_pct({연도: {연령대:%}})가
        담긴 dict.
    """
    gender = ims.tasis_gender_trend()
    age = ims.tasis_age_trend()
    return {
        "성별_비중_추이_pct": {str(y): v for y, v in gender.items()},
        "연령대_비중_추이_pct": {str(y): v for y, v in age.items()},
    }


TOOLS = [
    get_transaction_trend, get_jeonse_wolse_summary,
    list_cp_reference_data, get_cp_method_mix, get_cp_market_share, get_cp_composition_breakdown,
    get_office_open_close_stats, get_district_open_close_ranking, get_current_office_status_snapshot,
    get_industry_national_trend, get_industry_tam_estimate,
    get_tasis_snapshot, get_tasis_trend, get_industry_demographics_trend,
]
