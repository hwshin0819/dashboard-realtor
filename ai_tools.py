# -*- coding: utf-8 -*-
"""AI 에이전트가 Gemini function-calling으로 부르는 도구 함수들.
1차 범위는 '실거래량 동향' 데이터(매매/전세/월세)만 — real_estate_stats.py를 얇게 감싼다.
함수 시그니처의 타입힌트·docstring이 그대로 Gemini에 전달되는 함수 스펙이 되므로,
파라미터 설명을 사람이 아니라 모델이 읽는다는 전제로 정확하게 적는다."""
import region_utils as ru
import real_estate_stats as res

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


TOOLS = [get_transaction_trend, get_jeonse_wolse_summary]
