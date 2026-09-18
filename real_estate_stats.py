# -*- coding: utf-8 -*-
"""부동산 거래량 현황 메뉴의 실거래가 DB 조회/집계 레이어. real_stats.py와 같은 스타일로,
transaction_monthly(시군구 x 유형 x 거래유형 x 월)를 원하는 범위로 묶어서 돌려준다."""
from collections import defaultdict

import streamlit as st

import db
import region_utils as ru

# DB가 Supabase(네트워크 너머)라 매번 새로 쿼리하면 페이지 전환/위젯 조작마다 왕복 지연이 쌓인다.
# 수집기가 대략 시간 단위로 도는 정도라 5분 캐시면 최신성 손해는 거의 없이 체감 속도를 크게 줄인다.
_CACHE_TTL = 300

PROPERTY_TYPES = ["아파트", "오피스텔", "연립다세대", "단독다가구"]
TRADE_TYPES = ["매매", "전월세"]


@st.cache_data(ttl=_CACHE_TTL)
def has_any_data() -> bool:
    conn = db.get_conn()
    row = conn.execute("SELECT 1 FROM transaction_monthly LIMIT 1").fetchone()
    conn.close()
    return row is not None


@st.cache_data(ttl=_CACHE_TTL)
def load_sigungu_index() -> list:
    """offices 테이블에서 (시군구코드, 이름, 소속 시/도) 목록을 뽑는다. 지역 필터 드롭다운에 쓴다."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT DISTINCT ld_code, ld_code_nm FROM offices WHERE ld_code IS NOT NULL"
    ).fetchall()
    conn.close()
    return [
        {"code": r["ld_code"], "name": r["ld_code_nm"], "sido": ru.normalize_sido(r["ld_code_nm"])}
        for r in rows
    ]


def _codes_for_region(region_short: str):
    """'전국'이면 None(필터 없음), 특정 시/도면 그 안에 속한 시군구 코드 목록을 돌려준다."""
    if region_short == "전국":
        return None
    return _codes_for_sidos([region_short])


def _codes_for_sidos(sido_shorts):
    """sido_shorts가 None이면 전국(필터 없음), 리스트면 그 시/도들에 속한 시군구 코드를 전부 합쳐서 돌려준다.
    수도권(서울+경기+인천)처럼 여러 시/도를 하나로 묶어서 볼 때 쓴다."""
    if sido_shorts is None:
        return None
    full_names = {ru.FULL_NAME.get(s) for s in sido_shorts}
    return [r["code"] for r in load_sigungu_index() if r["sido"] in full_names]


def load_monthly_series(property_type: str = "전체", trade_type: str = "전체", region_short: str = "전국") -> list:
    """월별 [건수, 평균매매가, 평균보증금, 평균월세] 시계열 (월 오름차순).
    property_type: '전체' 또는 PROPERTY_TYPES 중 하나. trade_type: '전체' 또는 TRADE_TYPES 중 하나.
    여러 시군구/유형을 합칠 때는 건수 가중평균으로 금액을 합산한다."""
    return load_monthly_series_for_sidos(
        None if region_short == "전국" else [region_short], property_type, trade_type,
    )


@st.cache_data(ttl=_CACHE_TTL)
def load_monthly_series_for_sidos(sido_shorts, property_type: str = "전체", trade_type: str = "전체") -> list:
    """load_monthly_series와 동일하지만, 단일 시/도 대신 시/도 목록(예: 수도권=서울+경기+인천)을
    합쳐서 조회한다. sido_shorts=None이면 전국(필터 없음)."""
    codes = _codes_for_sidos(sido_shorts)
    conn = db.get_conn()
    q = "SELECT ym, sigungu_code, property_type, trade_type, count, avg_price, avg_deposit, avg_rent FROM transaction_monthly WHERE 1=1"
    params = []
    if property_type != "전체":
        q += " AND property_type=?"
        params.append(property_type)
    if trade_type != "전체":
        q += " AND trade_type=?"
        params.append(trade_type)
    if codes is not None:
        if not codes:
            conn.close()
            return []
        q += f" AND sigungu_code IN ({','.join('?' for _ in codes)})"
        params.extend(codes)
    rows = conn.execute(q, params).fetchall()
    conn.close()

    agg = defaultdict(lambda: {"count": 0, "price_sum": 0.0, "price_n": 0, "deposit_sum": 0.0, "deposit_n": 0, "rent_sum": 0.0, "rent_n": 0})
    for r in rows:
        a = agg[r["ym"]]
        c = r["count"] or 0
        a["count"] += c
        if r["avg_price"] is not None and c:
            a["price_sum"] += r["avg_price"] * c
            a["price_n"] += c
        if r["avg_deposit"] is not None and c:
            a["deposit_sum"] += r["avg_deposit"] * c
            a["deposit_n"] += c
        if r["avg_rent"] is not None and c:
            a["rent_sum"] += r["avg_rent"] * c
            a["rent_n"] += c

    out = [
        {
            "월": ym,
            "건수": a["count"],
            "평균매매가": round(a["price_sum"] / a["price_n"]) if a["price_n"] else None,
            "평균보증금": round(a["deposit_sum"] / a["deposit_n"]) if a["deposit_n"] else None,
            "평균월세": round(a["rent_sum"] / a["rent_n"]) if a["rent_n"] else None,
        }
        for ym, a in agg.items()
    ]
    out.sort(key=lambda r: r["월"])
    return out


@st.cache_data(ttl=_CACHE_TTL)
def type_breakdown(start_ym: str, end_ym: str, region_short: str = "전국") -> list:
    """선택 기간 누적 기준, 4개 유형별 매매/전월세 건수·평균금액·비중."""
    codes = _codes_for_region(region_short)
    conn = db.get_conn()
    q = "SELECT sigungu_code, property_type, trade_type, count, avg_price, avg_deposit FROM transaction_monthly WHERE ym BETWEEN ? AND ?"
    params = [start_ym, end_ym]
    if codes is not None:
        if not codes:
            conn.close()
            return [{"유형": p, "매매건수": 0, "전월세건수": 0, "매매평균가": None, "전월세평균보증금": None, "비중": 0.0} for p in PROPERTY_TYPES]
        q += f" AND sigungu_code IN ({','.join('?' for _ in codes)})"
        params.extend(codes)
    rows = conn.execute(q, params).fetchall()
    conn.close()

    agg = defaultdict(lambda: {"mae_count": 0, "jeon_count": 0, "mae_price_sum": 0.0, "mae_price_n": 0, "jeon_deposit_sum": 0.0, "jeon_deposit_n": 0})
    for r in rows:
        a = agg[r["property_type"]]
        c = r["count"] or 0
        if r["trade_type"] == "매매":
            a["mae_count"] += c
            if r["avg_price"] is not None and c:
                a["mae_price_sum"] += r["avg_price"] * c
                a["mae_price_n"] += c
        else:
            a["jeon_count"] += c
            if r["avg_deposit"] is not None and c:
                a["jeon_deposit_sum"] += r["avg_deposit"] * c
                a["jeon_deposit_n"] += c

    total = sum(a["mae_count"] + a["jeon_count"] for a in agg.values()) or 1
    out = []
    for ptype in PROPERTY_TYPES:
        a = agg.get(ptype, {"mae_count": 0, "jeon_count": 0, "mae_price_sum": 0, "mae_price_n": 0, "jeon_deposit_sum": 0, "jeon_deposit_n": 0})
        combined = a["mae_count"] + a["jeon_count"]
        out.append({
            "유형": ptype,
            "매매건수": a["mae_count"], "전월세건수": a["jeon_count"],
            "매매평균가": round(a["mae_price_sum"] / a["mae_price_n"]) if a["mae_price_n"] else None,
            "전월세평균보증금": round(a["jeon_deposit_sum"] / a["jeon_deposit_n"]) if a["jeon_deposit_n"] else None,
            "비중": round(combined / total * 100, 1),
        })
    return out
