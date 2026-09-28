# -*- coding: utf-8 -*-
"""
개요 탭에서 쓰는 실데이터 집계.
- 2026-08까지: realtor 저장소에서 이관한 legacy_monthly_stats (시도 단위, 개업/폐업만 있음)
- 2026-09부터: 우리가 직접 수집한 daily_region_stats (시군구 단위) 를 월/시도로 집계
두 구간을 이어 붙여서 하나의 월별·지역별(시도) 시계열로 돌려준다.
"""
from collections import defaultdict

import streamlit as st

import db
import region_utils as ru

LIVE_START_MONTH = "2026-09"

# DB가 Supabase(네트워크 너머)라 매번 새로 쿼리하면 왕복 지연이 쌓인다. 수집기가 대략 시간
# 단위로 도는 정도라 5분 캐시면 최신성 손해는 거의 없이 체감 속도를 크게 줄인다.
_CACHE_TTL = 300


def _load_active_snapshots(conn):
    """(월, 시도) -> 그 달 안에서 가장 최근 날짜의 영업중 합계.
    실제 daily_region_stats에 데이터가 있는 달이라면 legacy 기간(2026-08 이전)이라도 채워준다."""
    rows = conn.execute("SELECT date, region, active FROM daily_region_stats").fetchall()
    latest_date = {}  # (월,시도) -> 최신 날짜
    active_sum = {}  # (월,시도,날짜) -> 합계
    for r in rows:
        month = r["date"][:7]
        sido = ru.normalize_sido(r["region"])
        key = (month, sido)
        if key not in latest_date or r["date"] > latest_date[key]:
            latest_date[key] = r["date"]
        active_sum[(month, sido, r["date"])] = active_sum.get((month, sido, r["date"]), 0) + (r["active"] or 0)

    result = {}
    for key, d in latest_date.items():
        month, sido = key
        result[key] = active_sum.get((month, sido, d), 0)

    # '전국' 행은 그 달의 시도별 값을 모두 더해서 만든다 (raw 지역명이 '전국'으로 찍히는 경우는 없으므로).
    nation_totals = defaultdict(int)
    for (month, sido), value in result.items():
        nation_totals[month] += value
    for month, total in nation_totals.items():
        result[(month, "전국")] = total

    return result


@st.cache_data(ttl=_CACHE_TTL)
def load_active_snapshot_dates() -> dict:
    """(월, 지역짧은이름은 아니고 원래 지역표기) -> 그 달의 영업중 수치가 실제로 찍힌 날짜.
    카드에 '2026-09 기준' 대신 '2026-09-11 기준'처럼 정확한 날짜를 보여줄 때 쓴다."""
    conn = db.get_conn()
    rows = conn.execute("SELECT date, region FROM daily_region_stats").fetchall()
    conn.close()

    latest_date = {}
    for r in rows:
        month = r["date"][:7]
        sido = ru.normalize_sido(r["region"])
        key = (month, sido)
        if key not in latest_date or r["date"] > latest_date[key]:
            latest_date[key] = r["date"]

    nation_latest = defaultdict(str)
    for (month, sido), d in latest_date.items():
        if d > nation_latest[month]:
            nation_latest[month] = d
    for month, d in nation_latest.items():
        latest_date[(month, "전국")] = d

    return latest_date


def _load_legacy(conn, active_snapshots):
    rows = conn.execute(
        "SELECT month, region, opened, closed FROM legacy_monthly_stats"
    ).fetchall()
    out = []
    for r in rows:
        active = active_snapshots.get((r["month"], r["region"]))
        out.append(
            {"월": r["month"], "지역": r["region"], "개업": r["opened"], "폐업": r["closed"], "영업중": active, "출처": "backfill"}
        )
    return out


def _load_live_monthly(conn, active_snapshots):
    rows = conn.execute(
        "SELECT date, region, opened, closed FROM daily_region_stats WHERE date >= ?",
        (LIVE_START_MONTH,),
    ).fetchall()

    monthly_open_close = defaultdict(lambda: [0, 0])  # (월, 시도) -> [개업, 폐업]

    for r in rows:
        month = r["date"][:7]
        sido = ru.normalize_sido(r["region"])
        key = (month, sido)
        monthly_open_close[key][0] += r["opened"] or 0
        monthly_open_close[key][1] += r["closed"] or 0

    out = []
    for key, (opened, closed) in monthly_open_close.items():
        month, sido = key
        active = active_snapshots.get(key)
        out.append({"월": month, "지역": sido, "개업": opened, "폐업": closed, "영업중": active, "출처": "own"})

    # 시도별 합계를 그대로 더해서 '전국' 행을 만든다 (legacy 쪽에 있던 전국 합계와 형태를 맞춤)
    nation_totals = defaultdict(lambda: [0, 0, 0])  # month -> [개업, 폐업, 영업중]
    for row in out:
        t = nation_totals[row["월"]]
        t[0] += row["개업"]
        t[1] += row["폐업"]
        t[2] += row["영업중"] or 0
    for month, (opened, closed, active) in nation_totals.items():
        out.append({"월": month, "지역": "전국", "개업": opened, "폐업": closed, "영업중": active, "출처": "own"})

    return out


@st.cache_data(ttl=_CACHE_TTL)
def load_region_monthly_stats() -> list[dict]:
    conn = db.get_conn()
    active_snapshots = _load_active_snapshots(conn)
    rows = _load_legacy(conn, active_snapshots) + _load_live_monthly(conn, active_snapshots)
    conn.close()
    return rows


@st.cache_data(ttl=_CACHE_TTL)
def load_district_monthly_stats(sido_full: str) -> list[dict]:
    """특정 시도 안의 시군구별 월별 통계. 우리가 직접 수집한 날짜(daily_region_stats)에만 존재한다
    (과거 realtor 이력은 시도 단위까지만 있어서 시군구로는 쪼갤 수 없다)."""
    conn = db.get_conn()
    rows = conn.execute("SELECT date, region, active, opened, closed FROM daily_region_stats").fetchall()
    conn.close()

    monthly_open_close = defaultdict(lambda: [0, 0])  # (월, 시군구) -> [개업, 폐업]
    latest_date = {}
    active_sum = {}
    for r in rows:
        if ru.normalize_sido(r["region"]) != sido_full:
            continue
        month = r["date"][:7]
        key = (month, r["region"])
        monthly_open_close[key][0] += r["opened"] or 0
        monthly_open_close[key][1] += r["closed"] or 0
        if key not in latest_date or r["date"] > latest_date[key]:
            latest_date[key] = r["date"]
        active_sum[(key, r["date"])] = active_sum.get((key, r["date"]), 0) + (r["active"] or 0)

    out = []
    for key, (opened, closed) in monthly_open_close.items():
        month, district = key
        active = active_sum.get((key, latest_date[key]))
        out.append({"월": month, "지역": district, "개업": opened, "폐업": closed, "영업중": active, "출처": "own"})
    return out


@st.cache_data(ttl=_CACHE_TTL)
def load_all_district_monthly_stats() -> list[dict]:
    """전국 모든 시군구의 월별 통계 (시도 구분 없이 시군구명 원문 그대로 반환.
    ld_code_nm에 시도명이 포함돼 있어 시군구명이 겹쳐도 안전하다)."""
    conn = db.get_conn()
    rows = conn.execute("SELECT date, region, active, opened, closed FROM daily_region_stats").fetchall()
    conn.close()

    monthly_open_close = defaultdict(lambda: [0, 0])  # (월, 시군구) -> [개업, 폐업]
    latest_date = {}
    active_sum = {}
    for r in rows:
        region = r["region"]
        # 세종처럼 시군구 구분 없이 시/도 이름 자체만 있는 행은 시/도 합계 행과 중복되므로 제외한다.
        if not region or len(region.split()) < 2:
            continue
        month = r["date"][:7]
        key = (month, region)
        monthly_open_close[key][0] += r["opened"] or 0
        monthly_open_close[key][1] += r["closed"] or 0
        if key not in latest_date or r["date"] > latest_date[key]:
            latest_date[key] = r["date"]
        active_sum[(key, r["date"])] = active_sum.get((key, r["date"]), 0) + (r["active"] or 0)

    out = []
    for key, (opened, closed) in monthly_open_close.items():
        month, district = key
        active = active_sum.get((key, latest_date[key]))
        out.append({"월": month, "지역": district, "개업": opened, "폐업": closed, "영업중": active, "출처": "own"})
    return out


@st.cache_data(ttl=_CACHE_TTL)
def load_latest_snapshot_date() -> str | None:
    conn = db.get_conn()
    row = conn.execute("SELECT MAX(date) AS d FROM daily_region_stats").fetchone()
    conn.close()
    return row["d"] if row else None


@st.cache_data(ttl=_CACHE_TTL)
def load_agent_quarterly_stats() -> list[dict]:
    """개업공인중개사 현황(분기별, 분기말월 기준). 지역은 이미 짧은 이름(서울/경기/...)으로 저장돼 있다."""
    conn = db.get_conn()
    rows = conn.execute("SELECT month, region, count FROM agent_quarterly_stats ORDER BY month").fetchall()
    conn.close()
    return [{"월": r["month"], "지역": r["region"], "개업공인중개사": r["count"]} for r in rows]


def national_monthly_series() -> list[dict]:
    """전국 단위 월별 [개업, 폐업, 영업중] 시계열 (월 오름차순). MoM/YoY, 듀얼축 차트에 쓴다."""
    rows = [r for r in load_region_monthly_stats() if r["지역"] == "전국"]
    rows.sort(key=lambda r: r["월"])
    return rows


def estimate_active_series(rows: list[dict]) -> list[dict]:
    """'영업중' 실측 스냅샷이 없는 과거 달을, 가장 이른 실측값을 기준점 삼아 그 뒤 달과의
    순증감(개업-폐업)만큼 거꾸로 빼서 역산한 근사치로 채운다. rows는 월 오름차순이어야 한다.
    반환되는 각 행에 실측 여부를 나타내는 '영업중_추정'(bool)을 덧붙인다."""
    out = [dict(r) for r in rows]
    for r in out:
        r["영업중_추정"] = r.get("영업중") is None

    anchor_idx = next((i for i, r in enumerate(out) if r.get("영업중") is not None), None)
    if anchor_idx is None:
        return out

    running = out[anchor_idx]["영업중"]
    for i in range(anchor_idx - 1, -1, -1):
        nxt = out[i + 1]
        running = running - (nxt["개업"] or 0) + (nxt["폐업"] or 0)
        out[i]["영업중"] = running
    return out


def top_bottom_districts(period_months: list[str]) -> list[dict]:
    """선택 기간 동안 시군구별(ld_code_nm 원문) 개업/폐업/순증감 합계.
    시군구 데이터는 직접 수집을 시작한 2026-09월부터만 존재한다."""
    rows = load_all_district_monthly_stats()
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["월"] not in period_months:
            continue
        agg[r["지역"]][0] += r["개업"] or 0
        agg[r["지역"]][1] += r["폐업"] or 0
    return [
        {"지역": region, "개업": opened, "폐업": closed, "순증감": opened - closed}
        for region, (opened, closed) in agg.items()
    ]


@st.cache_data(ttl=_CACHE_TTL)
def load_latest_status_breakdown() -> dict:
    """전국 기준 최신 휴업/휴업연장/업무정지 건수 (현재는 지역별로 저장하지 않는다)."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT total_pause, total_ext, total_stop FROM collection_log ORDER BY collected_date DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return {"휴업": 0, "휴업연장": 0, "업무정지": 0}
    return {"휴업": row["total_pause"] or 0, "휴업연장": row["total_ext"] or 0, "업무정지": row["total_stop"] or 0}


@st.cache_data(ttl=_CACHE_TTL)
def load_office_status_counts() -> dict:
    """offices 테이블(현재 스냅샷) 기준 상태명별 건수. '중개사 현황' KPI 카드에 쓴다."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT sttus_se_code_nm, COUNT(*) c FROM offices GROUP BY sttus_se_code_nm"
    ).fetchall()
    conn.close()
    return {r["sttus_se_code_nm"]: r["c"] for r in rows}


@st.cache_data(ttl=_CACHE_TTL)
def load_new_offices_this_month() -> list[dict]:
    """이번 달(가장 최근 수집일 기준 월)에 등록일자가 찍힌 사무소 목록.
    B2B 신규 영업 타겟 리스트에 쓴다."""
    conn = db.get_conn()
    latest = conn.execute("SELECT MAX(date) d FROM daily_region_stats").fetchone()["d"]
    month = (latest or "")[:7]
    rows = conn.execute(
        "SELECT bsnm_cmpnm, ld_code_nm, regist_de FROM offices WHERE regist_de LIKE ? ORDER BY regist_de DESC",
        (f"{month}%",),
    ).fetchall()
    conn.close()
    return [{"상호명": r["bsnm_cmpnm"], "법정동": r["ld_code_nm"], "등록일자": r["regist_de"]} for r in rows]
