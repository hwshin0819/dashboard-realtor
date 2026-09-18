# -*- coding: utf-8 -*-
"""부동산 거래량 현황: 국토부 실거래가(아파트/오피스텔/연립다세대/단독다가구 x 매매/전월세) 메뉴."""
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import auth
import real_estate_stats as res
import region_utils as ru
from theme import CARD, GREEN, INK, LINE, MUTED

_PILL_GREEN = "#027A48"  # 빠른 선택 버튼 선택 상태 강조색 (경영진 보고용 배색 지침)

# 거래량 추이 차트 팔레트 — 매매(짙은 블루)·전월세(연한 베이지그레이)를 쌓고, 매매 평균 거래금액만 코랄선으로
# 겹쳐서 "매매 시세 흐름"이 또렷하게 보이도록 한다(전세/월세 보증금을 섞은 값은 오해 소지가 있어 쓰지 않는다).
_BAR_MAE = "#2B4C7E"
_BAR_JEON = "#D9E2EC"
_LINE_PRICE = "#F97316"

# 이 페이지 전용 CSS — 전부 .st-key-transactions_root로 스코프를 걸어 다른 페이지엔 영향 없음.
_EXTRA_CSS = f"""
<style>
.st-key-transactions_root .ov-stats {{ grid-template-columns:repeat(3,1fr); }}
.st-key-transactions_root .ov-stats.ov-stats-peak {{ grid-template-columns:repeat(4,1fr); }}
@media (max-width:900px) {{
    .st-key-transactions_root .ov-stats {{ grid-template-columns:repeat(1,1fr); }}
}}

/* 빠른 선택(segmented_control): 선택된 것만 초록 배경+흰 글자, 나머진 회색 테두리 */
.st-key-transactions_root .st-key-re_preset button[data-variant="segmented_control"] {{
    border: 1.5px solid {LINE} !important;
    background: {CARD} !important;
    border-radius: 8px !important;
}}
.st-key-transactions_root .st-key-re_preset button[data-variant="segmented_control"] p {{
    color: {MUTED} !important; font-weight: 500 !important;
}}
.st-key-transactions_root .st-key-re_preset button[data-variant="segmented_control"][data-selected="true"] {{
    background: {_PILL_GREEN} !important; border-color: {_PILL_GREEN} !important;
}}
.st-key-transactions_root .st-key-re_preset button[data-variant="segmented_control"][data-selected="true"] p {{
    color: #fff !important; font-weight: 700 !important;
}}
</style>
"""


def _apply_preset(all_months: list, confirmed_month: str):
    preset = st.session_state.get("re_preset")
    if preset is None:
        return
    idx = all_months.index(confirmed_month)
    year_start = f"{confirmed_month[:4]}-01"
    year_start = year_start if year_start in all_months else all_months[0]
    mapping = {
        "최근 6개월": (all_months[max(0, idx - 5)], confirmed_month),
        "올해": (year_start, confirmed_month),
        "최근 12개월": (all_months[max(0, idx - 11)], confirmed_month),
        "전체": (all_months[0], confirmed_month),
    }
    start, end = mapping[preset]
    st.session_state["re_start"] = start
    st.session_state["re_end"] = end


def _change_vs_base(series: list, base_month: str, latest_month: str) -> dict | None:
    """월별 시계열(건수 포함)에서 기준월(base_month)과 확정월(latest_month)을 비교해 등락률을 계산한다."""
    if not series:
        return None
    base_row = next((r for r in series if r["월"] == base_month), None)
    latest_row = next((r for r in series if r["월"] == latest_month), None)
    if base_row is None or latest_row is None or not base_row["건수"]:
        return None
    base_count = base_row["건수"] or 0
    latest_count = latest_row["건수"] or 0
    pct = (latest_count - base_count) / base_count * 100
    return {
        "base_month": base_month, "base_count": base_count,
        "latest_month": latest_month, "latest_count": latest_count, "pct": pct,
    }


def _quarter_label(ym: str) -> str:
    y, m = ym.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}-Q{q}"


def _build_trend_rows(mae_rows: list, jeon_rows: list, period_months: list) -> list:
    """매매/전월세 시리즈를 월 기준으로 합쳐 [월, 매매건수, 전월세건수, 매매평균가] 행으로 만든다."""
    by_month = {m: {"매매건수": 0, "전월세건수": 0, "매매평균가": None} for m in period_months}
    for r in mae_rows:
        if r["월"] in by_month:
            by_month[r["월"]]["매매건수"] = r["건수"] or 0
            by_month[r["월"]]["매매평균가"] = r["평균매매가"]
    for r in jeon_rows:
        if r["월"] in by_month:
            by_month[r["월"]]["전월세건수"] = r["건수"] or 0
    return [{"월": m, **by_month[m]} for m in period_months]


def _aggregate_trend(rows: list, quarterly: bool) -> list:
    """월별 추이 행을 그대로 두거나(quarterly=False), 분기 단위로 묶는다.
    거래량은 합계, 가격은 매매 건수 가중평균으로 집계한다."""
    if not quarterly or not rows:
        return rows
    agg = defaultdict(lambda: {"매매건수": 0, "전월세건수": 0, "amt_sum": 0.0, "amt_n": 0})
    for r in rows:
        a = agg[_quarter_label(r["월"])]
        a["매매건수"] += r["매매건수"] or 0
        a["전월세건수"] += r["전월세건수"] or 0
        if r["매매평균가"] is not None and r["매매건수"]:
            a["amt_sum"] += r["매매평균가"] * r["매매건수"]
            a["amt_n"] += r["매매건수"]
    out = [
        {
            "월": k, "매매건수": a["매매건수"], "전월세건수": a["전월세건수"],
            "매매평균가": round(a["amt_sum"] / a["amt_n"]) if a["amt_n"] else None,
        }
        for k, a in agg.items()
    ]
    out.sort(key=lambda r: r["월"])
    return out


def _trend_chart(rows: list) -> go.Figure:
    """누적 막대(매매+전월세=총거래량) + 매매 평균 거래금액 꺾은선, 이중 축."""
    df = pd.DataFrame(rows)
    fig = go.Figure()
    fig.add_bar(x=df["월"], y=df["매매건수"], name="매매", marker_color=_BAR_MAE)
    fig.add_bar(x=df["월"], y=df["전월세건수"], name="전월세", marker_color=_BAR_JEON)
    fig.add_trace(go.Scatter(
        x=df["월"], y=df["매매평균가"], name="매매 평균 거래금액",
        mode="lines+markers", line=dict(color=_LINE_PRICE, width=2.5), yaxis="y2",
    ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=12),
        xaxis=dict(gridcolor=LINE),
        yaxis=dict(title="거래량(건)", gridcolor=LINE, zerolinecolor=LINE, tickformat=","),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, tickformat=",", tickfont=dict(color=_LINE_PRICE)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=10, b=10),
        height=400,
        dragmode=False,
    )
    return fig


def render():
    if not res.has_any_data():
        st.title(auth.PAGE_TRANSACTIONS)
        st.info(
            "아직 수집된 실거래가 데이터가 없습니다. 프로젝트 루트의 `.env`에 "
            "`DATA_GO_KR_SERVICE_KEY`를 설정한 뒤 `python collect_transaction_volume.py`를 "
            "실행해 데이터를 수집해주세요. (전국 10개년 백필은 호출량이 많아 여러 번 나눠 실행됩니다.)"
        )
        return

    idx = res.load_sigungu_index()
    all_series = res.load_monthly_series("전체", "전체", "전국")
    all_months = [r["월"] for r in all_series]
    if not all_months:
        st.title(auth.PAGE_TRANSACTIONS)
        st.info("표시할 데이터가 없습니다.")
        return
    latest_month = all_months[-1]
    # 실거래가 신고기한(계약 후 30일 이내)상 당월 데이터는 집계 중(잠정치)이므로, KPI/기본조회 기준은
    # 그 이전 달(확정월)로 잡는다 — 당월을 기준으로 삼으면 "거래량이 갑자기 뚝 떨어진 것"처럼 왜곡되어 보인다.
    confirmed_month = all_months[-2] if len(all_months) > 1 else all_months[-1]
    is_provisional = latest_month != confirmed_month
    regions_short = ["전국"] + ru.ordered_short_regions({r["sido"] for r in idx})

    with st.container(key="transactions_root"):
        st.markdown(_EXTRA_CSS, unsafe_allow_html=True)

        st.markdown(
            f'<div class="ov-topline"><h1 style="margin:0;">{auth.PAGE_TRANSACTIONS}</h1></div>',
            unsafe_allow_html=True,
        )

        # ---- 필터 상태 기본값(KPI가 필터보다 먼저 그려지므로, 위젯 만들기 전에 session_state부터 채운다) ----
        idx_confirmed = all_months.index(confirmed_month)
        st.session_state.setdefault("re_region", "전국")
        st.session_state.setdefault("re_start", all_months[0])
        st.session_state.setdefault("re_end", confirmed_month)
        st.session_state.setdefault("re_preset", "전체")

        region_short = st.session_state["re_region"]
        start_month, end_month = st.session_state["re_start"], st.session_state["re_end"]
        if start_month > end_month:
            start_month, end_month = end_month, start_month
        property_type = "전체"

        # ---- 통합 필터바 (지역·시작·종료·빠른선택을 카드 한 줄로) ----
        with st.container(border=True):
            f1, f2, f3, f4 = st.columns([1, 0.8, 0.8, 1.8])
            region_short = f1.selectbox("지역", regions_short, key="re_region")
            start_month = f2.selectbox("시작", all_months, key="re_start")
            end_month = f3.selectbox("종료", all_months, key="re_end")
            f4.segmented_control(
                "빠른 선택", options=["최근 6개월", "올해", "최근 12개월", "전체"],
                key="re_preset", on_change=_apply_preset, args=(all_months, confirmed_month),
            )

        if start_month > end_month:
            start_month, end_month = end_month, start_month
        period_months = [m for m in all_months if start_month <= m <= end_month]

        series_all = res.load_monthly_series(property_type, "전체", region_short)
        period_series = [r for r in series_all if r["월"] in period_months]
        mae_series = res.load_monthly_series(property_type, "매매", region_short)
        jeon_series = res.load_monthly_series(property_type, "전월세", region_short)

        # ---- KPI 카드 3개 (총량 -> 매매 -> 전월세 흐름) ----
        total_count = sum(r["건수"] for r in period_series)

        mae_count = sum(r["건수"] for r in mae_series if r["월"] in period_months)
        jeon_count = sum(r["건수"] for r in jeon_series if r["월"] in period_months)
        mae_share = (mae_count / total_count * 100) if total_count else 0.0
        jeon_share = (jeon_count / total_count * 100) if total_count else 0.0

        cards_html = (
            '<div class="ov-stats">'
            + '<div class="ov-stat open"><div class="label">기간 내 총 거래량</div>'
              f'<div class="value">{total_count:,}건</div><div class="delta">매매 + 전월세 합산</div></div>'
            + '<div class="ov-stat"><div class="label">매매 거래량</div>'
              f'<div class="value">{mae_count:,}건</div><div class="delta">전체 중 비중 {mae_share:.1f}%</div></div>'
            + '<div class="ov-stat"><div class="label">전월세 거래량</div>'
              f'<div class="value">{jeon_count:,}건</div><div class="delta">전체 중 비중 {jeon_share:.1f}%</div></div>'
            + "</div>"
        )
        st.markdown(cards_html, unsafe_allow_html=True)

        # ---- 전세/월세 평균 보증금·평균 월세 (선택한 지역·기간 기준) ----
        jw = res.jeonse_wolse_summary(start_month, end_month, region_short)
        jw_cards_html = (
            '<div class="ov-stats">'
            + '<div class="ov-stat"><div class="label">전세 평균 보증금</div>'
              + (f'<div class="value">{jw["전세평균보증금"]:,}만원</div><div class="delta">전세 {jw["전세건수"]:,}건 기준</div></div>'
                 if jw["전세평균보증금"] is not None else '<div class="value">–</div><div class="delta">데이터 없음</div></div>')
            + '<div class="ov-stat"><div class="label">월세 평균 보증금</div>'
              + (f'<div class="value">{jw["월세평균보증금"]:,}만원</div><div class="delta">월세 {jw["월세건수"]:,}건 기준</div></div>'
                 if jw["월세평균보증금"] is not None else '<div class="value">–</div><div class="delta">데이터 없음</div></div>')
            + '<div class="ov-stat"><div class="label">평균 월세</div>'
              + (f'<div class="value">{jw["평균월세"]:,}만원</div><div class="delta">월세 {jw["월세건수"]:,}건 기준</div></div>'
                 if jw["평균월세"] is not None else '<div class="value">–</div><div class="delta">데이터 없음</div></div>')
            + "</div>"
        )
        st.markdown(jw_cards_html, unsafe_allow_html=True)

        # ---- 2020-06 대비 매매 거래량 (전국/서울/수도권/지방) ----
        BASE_MONTH = "2020-06"
        COMPARE_MONTH = "2026-06"
        peak_groups = [
            ("전국", None),
            ("서울", ["서울"]),
            ("수도권", ru.METRO_SIDOS),
            ("지방", ru.NON_METRO_SIDOS),
        ]
        peak_cards = []
        for label, sidos in peak_groups:
            stat = _change_vs_base(res.load_monthly_series_for_sidos(sidos, "전체", "매매"), BASE_MONTH, COMPARE_MONTH)
            if stat is None:
                peak_cards.append(
                    f'<div class="ov-stat"><div class="label">{label} 매매 거래량 ({BASE_MONTH} 대비)</div>'
                    '<div class="value">–</div><div class="delta">데이터 없음</div></div>'
                )
                continue
            cls = "close" if stat["pct"] < 0 else "open"
            peak_cards.append(
                f'<div class="ov-stat {cls}"><div class="label">{label} 매매 거래량 ({BASE_MONTH} 대비)</div>'
                f'<div class="value">{stat["pct"]:+.1f}%</div>'
                f'<div class="delta">{stat["base_month"]} {stat["base_count"]:,}건 → '
                f'{stat["latest_month"]} {stat["latest_count"]:,}건</div></div>'
            )
        st.markdown('<div class="ov-stats ov-stats-peak">' + "".join(peak_cards) + "</div>", unsafe_allow_html=True)

        # ---- 서브탭 ----
        tabA, tabB = st.tabs(["거래량 추이", "유형별 현황"])

        with tabA:
            with st.container(border=True):
                h1, h2 = st.columns([3, 1])
                h1.markdown('<div class="ov-panel-title">매매·전월세 거래량 추이</div>', unsafe_allow_html=True)
                h1.markdown(
                    '<div class="ov-panel-desc">누적 막대: 매매(진한 블루) + 전월세(연한 그레이) = 총 거래량(건)<br>'
                    '코랄선: 매매 평균 거래금액(만원)</div>', unsafe_allow_html=True,
                )
                with h2:
                    st.markdown('<div style="height:.3rem"></div>', unsafe_allow_html=True)
                    with st.container(key="ov_unit_toggle"):
                        quarterly = st.radio(
                            "단위", ["월별", "분기별"], horizontal=True, label_visibility="collapsed", key="re_unit",
                        ) == "분기별"

                trend_rows = _build_trend_rows(mae_series, jeon_series, period_months)
                if not trend_rows:
                    st.info("선택한 조건에 해당하는 데이터가 없습니다.")
                else:
                    agg = _aggregate_trend(trend_rows, quarterly)
                    fig = _trend_chart(agg)
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

                if is_provisional:
                    st.caption("※ 당월 데이터는 실거래가 신고 기한 미전결 상태로 집계 중입니다.")
                st.caption("출처: 국토교통부 실거래가 공개시스템")

        with tabB:
            with st.container(border=True):
                st.markdown('<div class="ov-panel-title">유형별 현황</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="ov-panel-desc">{start_month} ~ {end_month} 누적 기준</div>', unsafe_allow_html=True)
                breakdown = res.type_breakdown(start_month, end_month, region_short)

                fig_bar = go.Figure(go.Bar(
                    x=[b["비중"] for b in breakdown], y=[b["유형"] for b in breakdown],
                    orientation="h", marker_color=GREEN,
                    text=[f"{b['비중']:.1f}%" for b in breakdown], textposition="outside",
                ))
                fig_bar.update_layout(
                    plot_bgcolor=CARD, paper_bgcolor=CARD,
                    font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=12),
                    xaxis=dict(title="비중(%)", gridcolor=LINE),
                    margin=dict(l=10, r=30, t=10, b=10), height=220, dragmode=False,
                )
                st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

                table_df = pd.DataFrame([
                    {
                        "유형": b["유형"],
                        "매매 건수": f"{b['매매건수']:,}",
                        "매매 평균가(만원)": "–" if b["매매평균가"] is None else f"{b['매매평균가']:,}",
                        "전월세 건수": f"{b['전월세건수']:,}",
                        "전월세 평균보증금(만원)": "–" if b["전월세평균보증금"] is None else f"{b['전월세평균보증금']:,}",
                        "비중": f"{b['비중']:.1f}%",
                    }
                    for b in breakdown
                ])
                st.dataframe(table_df, use_container_width=True, hide_index=True)
