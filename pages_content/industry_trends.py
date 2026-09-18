# -*- coding: utf-8 -*-
"""부동산중개업 시장 동향: KOSIS(서비스업조사) 전국 연도별 추이(탭1) + TASIS(국세통계포털) 시/도·시/군/구별
연도별(2021~2025) 현황(탭2, 지도 클릭으로 시/군/구 드릴다운). 데이터는 industry_market_stats.py와
data/tasis_lifestyle_058.json에 고정값으로 들어있다 — 새 연도 자료가 나오면 그 파일만 갱신한다."""
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import auth
import industry_market_stats as ims
import region_utils as ru
from theme import BLUE, CARD, GREEN, GREEN_DEEP, INK, LINE, MUTED, VERMILION

_KOREA_LAT_RANGE = [32.8, 38.8]
_KOREA_LON_RANGE = [124.4, 131.0]

# 지역별 현황 탭의 시/도·시/군/구 상세표를 화면에서 숨긴다(데이터/로직은 그대로 두고 노출만 끔).
# 다시 보이게 하려면 True로 바꾸면 된다.
_SHOW_TASIS_DETAIL_TABLE = False


@st.cache_data
def _load_geojson() -> dict:
    with open(ims.geojson_path(), encoding="utf-8") as f:
        return json.load(f)


_UNSELECTED_BAR = "#C9D6CE"


def _national_trend_chart(rows: list, selected_years: tuple = None) -> go.Figure:
    """selected_years=(시작연도, 끝연도)를 주면 그 구간의 막대만 진하게, 나머지는 흐리게 처리해
    드래그로 고른 구간이 시각적으로 도드라지게 한다. dragmode='select'라 그래프 위 드래그가
    바로 박스 선택(구간 선택)으로 이어진다."""
    df = pd.DataFrame(rows)
    if selected_years:
        lo, hi = selected_years
        in_range = df["연도"].apply(lambda y: lo <= y <= hi)
        bar_colors = [GREEN if v else _UNSELECTED_BAR for v in in_range]
        bar_opacity = [1.0 if v else 0.55 for v in in_range]
    else:
        bar_colors = [GREEN] * len(df)
        bar_opacity = [1.0] * len(df)

    fig = go.Figure()

    # 녹색 배경 영역 — 드래그 선택으로 막대가 흐려져도 전체 추이의 실루엣은 항상 그대로 보이게.
    fig.add_trace(go.Scatter(
        x=df["연도"], y=df["매출액"] / 1_000_000, mode="lines",
        fill="tozeroy", line=dict(color=GREEN, width=0),
        fillcolor="rgba(14,122,68,0.14)", hoverinfo="skip", showlegend=False,
    ))

    fig.add_bar(
        x=df["연도"], y=df["매출액"] / 1_000_000, name="총매출액(조원)",
        marker=dict(color=bar_colors, opacity=bar_opacity),
        text=[f"{v/1_000_000:.1f}조" for v in df["매출액"]], textposition="inside",
        insidetextanchor="end", textfont=dict(color="#FFFFFF"),
    )
    fig.add_trace(go.Scatter(
        x=df["연도"], y=df["평균매출_만원"], name="사업체당 평균매출(만원)",
        mode="lines+markers+text", line=dict(color=INK, width=2.5), yaxis="y2",
        text=[f"{v:,}만원" for v in df["평균매출_만원"]], textposition="top center",
        textfont=dict(color=INK, size=11),
    ))
    fig.add_trace(go.Scatter(
        x=df["연도"], y=df["영업이익_만원"], name="업체당 영업이익(만원)",
        mode="lines+markers", line=dict(color=_KOSIS_COLOR, width=2, dash="dash"),
        marker=dict(symbol="diamond", size=6), yaxis="y2", connectgaps=False,
        hovertemplate="%{x}년 · 업체당 영업이익 %{y:,.0f}만원<extra></extra>",
    ))

    fig.update_layout(
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=12),
        xaxis=dict(gridcolor=LINE, tickmode="array", tickvals=df["연도"], title="연도"),
        yaxis=dict(title="총매출액(조원)", gridcolor=LINE, zerolinecolor=LINE),
        yaxis2=dict(title="평균매출·영업이익(만원)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=30, b=10),
        height=380,
        dragmode="select",
        selectdirection="h",
    )
    return fig


def _regional_map(rows: list, lat_range: list = None, lon_range: list = None) -> go.Figure:
    """시/도 버블맵. rows가 '지역'(시/도, SIDO_LATLON 좌표)이든 '시군구'(위경도 직접 포함)든 다 그린다.
    lat_range/lon_range를 주면 그 범위로 확대(드릴다운용), 안 주면 전국 범위."""
    geo = _load_geojson()
    codes = [f["properties"]["code"] for f in geo["features"]]
    is_district = "시군구" in rows[0] if rows else False
    labels = [r["시군구"] if is_district else r["지역"] for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Choropleth(
        geojson=geo, locations=codes, z=[0] * len(codes),
        featureidkey="properties.code",
        colorscale=[[0, "#EEF2ED"], [1, "#EEF2ED"]], showscale=False,
        marker_line_color=LINE, marker_line_width=1,
        hoverinfo="skip",
    ))

    values = [r["평균연매출"] for r in rows]
    max_v = max(values) if values else 1
    lats = [r["lat"] for r in rows] if is_district else [ru.SIDO_LATLON[r["지역"]][0] for r in rows]
    lons = [r["lon"] for r in rows] if is_district else [ru.SIDO_LATLON[r["지역"]][1] for r in rows]
    fig.add_trace(go.Scattergeo(
        lon=lons, lat=lats, text=labels, customdata=labels,
        mode="markers+text",
        marker=dict(
            size=[14 + 40 * (v / max_v) ** 0.5 for v in values],
            color=GREEN, opacity=0.75, line=dict(color=GREEN_DEEP, width=1),
        ),
        textposition="middle center",
        textfont=dict(size=9 if is_district else 10, color="#FFFFFF"),
        hovertext=[
            f"{lbl}<br>평균 연매출 {r['평균연매출']:,}만원"
            for lbl, r in zip(labels, rows)
        ],
        hoverinfo="text",
        name="",
    ))

    fig.update_geos(
        visible=False, showcountries=False, showcoastlines=False, showland=False,
        lataxis_range=lat_range or _KOREA_LAT_RANGE, lonaxis_range=lon_range or _KOREA_LON_RANGE,
        projection_type="mercator", bgcolor=CARD,
    )
    fig.update_layout(
        paper_bgcolor=CARD, showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0), height=520,
        clickmode="event+select",
    )
    return fig


def _regional_rank_chart(rows: list, national_avg: int = None) -> go.Figure:
    label_key = "시군구" if (rows and "시군구" in rows[0]) else "지역"
    ordered = sorted(rows, key=lambda r: r["평균연매출"])
    fig = go.Figure(go.Bar(
        x=[r["평균연매출"] for r in ordered], y=[r[label_key] for r in ordered],
        orientation="h", marker_color=GREEN,
        text=[f"{r['평균연매출']:,}만원" for r in ordered], textposition="inside",
        insidetextanchor="end", textfont=dict(color="#FFFFFF"),
    ))
    if national_avg is not None:
        fig.add_vline(
            x=national_avg, line=dict(color=INK, width=1.5, dash="dash"),
            annotation_text=f"전국 평균 {national_avg:,}만원", annotation_position="top",
            annotation_font=dict(size=10, color=INK),
        )
    fig.update_layout(
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=11),
        xaxis=dict(title="평균 연매출(만원)", gridcolor=LINE),
        margin=dict(l=10, r=30, t=30, b=10), height=max(320, 22 * len(ordered) + 60), dragmode=False,
    )
    return fig


def _fmt_pct(v) -> str:
    return "–" if v is None else f"{v:+.2f}"


def _trend_heatmap(trend: dict, pin_first: str = None) -> go.Figure:
    """{이름: {연도: 평균연매출}} 딕셔너리를 지역/시군구(행) x 연도(열) 히트맵으로 그린다.
    최신 연도 값이 큰 순서로 행을 정렬하고, pin_first로 준 이름(예: '전국')이 있으면 맨 위에 고정한다.
    라인차트는 10개 넘는 지역을 한 화면에서 비교하기 어려워, 색 진하기로 한눈에 훑어볼 수 있게 했다."""
    years = sorted({y for series in trend.values() for y in series})
    names = [n for n in trend if n != pin_first]
    names.sort(key=lambda n: -(trend[n].get(years[-1]) or 0))
    if pin_first and pin_first in trend:
        names = [pin_first] + names

    z = [[trend[n].get(y) for y in years] for n in names]
    text = [[f"{v:,}" if v is not None else "–" for v in row] for row in z]

    fig = go.Figure(go.Heatmap(
        z=z, x=years, y=names, text=text, texttemplate="%{text}",
        colorscale=[[0, "#EAF3EE"], [1, GREEN_DEEP]],
        showscale=False, xgap=3, ygap=3,
        textfont=dict(size=10, color=INK),
        hovertemplate="%{y} · %{x}년<br>평균 연매출 %{z:,}만원<extra></extra>",
    ))
    fig.update_layout(
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=11),
        xaxis=dict(side="top", tickmode="array", tickvals=years, showgrid=False),
        yaxis=dict(autorange="reversed", showgrid=False),
        margin=dict(l=10, r=10, t=30, b=10),
        height=max(320, 26 * len(names) + 60),
    )
    return fig


_LINE_PALETTE = [
    GREEN, BLUE, VERMILION, "#B8860B", "#6B4FA0", "#0E9AA7",
    "#D97706", "#7B8B6F", "#A83279", "#4C6EF5", "#2F855A", "#9C4221",
]


def _trend_line_chart(trend: dict, pin_first: str = None) -> go.Figure:
    """{이름: {연도: 평균연매출}}을 지역/시군구별 선 그래프로 그린다. 히트맵이 '한눈에 개요'라면
    이쪽은 궤적(오르내리는 모양)을 정확히 보기 위한 대안이다. pin_first(예: '전국')는 검정 굵은 선으로 강조."""
    years = sorted({y for series in trend.values() for y in series})
    names = [n for n in trend if n != pin_first]
    names.sort(key=lambda n: -(trend[n].get(years[-1]) or 0))

    fig = go.Figure()
    for i, name in enumerate(names):
        vals = [trend[name].get(y) for y in years]
        fig.add_trace(go.Scatter(
            x=years, y=vals, name=name, mode="lines+markers",
            line=dict(color=_LINE_PALETTE[i % len(_LINE_PALETTE)], width=1.8),
            marker=dict(size=5), connectgaps=False,
        ))
    if pin_first and pin_first in trend:
        vals = [trend[pin_first].get(y) for y in years]
        fig.add_trace(go.Scatter(
            x=years, y=vals, name=pin_first, mode="lines+markers",
            line=dict(color=INK, width=3), marker=dict(size=7), connectgaps=False,
        ))

    fig.update_layout(
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=11),
        xaxis=dict(gridcolor=LINE, tickmode="array", tickvals=years),
        yaxis=dict(title="평균 연매출(만원)", gridcolor=LINE),
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0, font=dict(size=9)),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=20, b=10), height=420, dragmode=False,
    )
    return fig


_AGE_COLORS = ["#EAF3EE", "#C7E1D2", "#8FC7A9", "#4FA378", GREEN, GREEN_DEEP]


def _age_stack_chart(age_trend: dict) -> go.Figure:
    """연령대별 비중 100% 누적 막대. 젊을수록 연한 색, 나이 들수록 짙은 초록으로 고령화 추세가 눈에 보이게 했다."""
    years = sorted(age_trend.keys())
    fig = go.Figure()
    for bracket, color in zip(ims.AGE_BRACKET_ORDER, _AGE_COLORS):
        vals = [age_trend[y][bracket] for y in years]
        fig.add_bar(
            x=years, y=vals, name=bracket, marker_color=color,
            text=[f"{v:.0f}%" if v >= 5 else "" for v in vals], textposition="inside",
            textfont=dict(size=9, color="#FFFFFF" if color in (GREEN, GREEN_DEEP) else INK),
        )
    fig.update_layout(
        barmode="stack",
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=11),
        xaxis=dict(gridcolor=LINE, tickmode="array", tickvals=years),
        yaxis=dict(title="비중(%)", gridcolor=LINE, range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=9)),
        margin=dict(l=10, r=10, t=30, b=10), height=340, dragmode=False,
    )
    return fig


def _gender_line_chart(gender_trend: dict) -> go.Figure:
    """남/여 비중 추이. 두 선이 좁혀지는 모습(여성 비중 증가)을 보여주려 라인차트로 그렸다."""
    years = sorted(gender_trend.keys())
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years, y=[gender_trend[y]["남자"] for y in years], name="남자",
        mode="lines+markers+text", line=dict(color=BLUE, width=2.5),
        text=[f"{gender_trend[y]['남자']:.1f}%" for y in years], textposition="top center",
        textfont=dict(size=10, color=BLUE),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=[gender_trend[y]["여자"] for y in years], name="여자",
        mode="lines+markers+text", line=dict(color=VERMILION, width=2.5),
        text=[f"{gender_trend[y]['여자']:.1f}%" for y in years], textposition="bottom center",
        textfont=dict(size=10, color=VERMILION),
    ))
    fig.update_layout(
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Pretendard Variable, Pretendard, sans-serif", color=INK, size=11),
        xaxis=dict(gridcolor=LINE, tickmode="array", tickvals=years),
        yaxis=dict(title="비중(%)", gridcolor=LINE, range=[40, 60]),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        margin=dict(l=10, r=10, t=30, b=10), height=340, dragmode=False,
    )
    return fig


_KOSIS_COLOR = "#D97706"  # 주황


def _render_national_tab():
    """탭: 전국 시장 현황 — TAM/21년 고점 대비 요약 카드 + 통계청 전국 추이(드래그 구간비교,
    영업이익 포함) + 인력 구조(국세청) + 원본 수치 표를 한 화면에 모았다. 예전엔 '시장 규모 요약'과
    '전국 추이 현황' 탭이 따로 있었는데, 둘 다 같은 통계청 전국 데이터를 카드/그래프로만 나눠 보여줘서
    중복이라 하나로 합쳤다."""
    st.markdown(
        f'<div style="text-align:right; color:{MUTED}; font-size:.8rem;">개인+법인 · 2017~2024년 · 통계청 서비스업조사 기준</div>',
        unsafe_allow_html=True,
    )
    band = ims.tam_band()
    trend = ims.national_trend()
    kosis_latest = trend[-1]
    kosis_2021 = next(r for r in trend if r["연도"] == 2021)

    revenue_chg_pct = (kosis_latest["매출액"] - kosis_2021["매출액"]) / kosis_2021["매출액"] * 100
    firms_chg_pct = (kosis_latest["사업체수"] - kosis_2021["사업체수"]) / kosis_2021["사업체수"] * 100
    avg_chg_pct = (kosis_latest["평균매출_만원"] - kosis_2021["평균매출_만원"]) / kosis_2021["평균매출_만원"] * 100

    cards_html = (
        '<div class="ov-stats">'
        + '<div class="ov-stat"><div class="label">전국 시장 규모 (TAM/총매출액)</div>'
          f'<div class="value">약 {band["avg3_조원"]:.1f}조원</div>'
          f'<div class="delta">{band["years3"][0]}~{band["years3"][-1]}년 평균 · 범위 '
          f'{band["lo_조원"]:.1f}~{band["hi_조원"]:.1f}조원({band["years4"][0]}~{band["years4"][-1]}년)</div></div>'
        + '<div class="ov-stat close"><div class="label">총매출 (21년 고점 대비)</div>'
          f'<div class="value">{_fmt_pct(revenue_chg_pct)}%</div>'
          f'<div class="delta">{kosis_2021["매출액"]/1_000_000:.1f}조원 → {kosis_latest["매출액"]/1_000_000:.1f}조원</div></div>'
        + '<div class="ov-stat close"><div class="label">업체당 평균매출 (21년 고점 대비)</div>'
          f'<div class="value">{_fmt_pct(avg_chg_pct)}%</div>'
          f'<div class="delta">{kosis_2021["평균매출_만원"]:,}만원 → {kosis_latest["평균매출_만원"]:,}만원</div></div>'
        + '<div class="ov-stat close"><div class="label">사업체 수 (21년 고점 대비)</div>'
          f'<div class="value">{_fmt_pct(firms_chg_pct)}%</div>'
          f'<div class="delta">{kosis_2021["사업체수"]:,}개 → {kosis_latest["사업체수"]:,}개</div></div>'
        + "</div>"
    )
    st.markdown(cards_html, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<div class="ov-panel-title">전국 부동산 중개 및 대리업(KSIC 68221) 매출 추이</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="ov-panel-desc">녹색 영역·막대: 총매출액(조원, 왼쪽 축) · 검정 실선: 사업체당 평균매출(만원, 오른쪽 축) · '
            '주황 점선: 업체당 영업이익(만원, 오른쪽 축)<br>'
            '2020년은 서비스업조사가 경제총조사로 대체되는 해라 자료가 없음</div>',
            unsafe_allow_html=True,
        )
        sel = st.session_state.get("kosis_trend_selection")
        event = st.plotly_chart(
            _national_trend_chart(trend, selected_years=sel),
            use_container_width=True, config={"displayModeBar": False},
            on_select="rerun", selection_mode="box",
            key="kosis_trend_chart",
        )
        if event and event["selection"]["points"]:
            picked = sorted({int(p["x"]) for p in event["selection"]["points"] if p.get("x") is not None})
            if len(picked) >= 2 and (picked[0], picked[-1]) != sel:
                st.session_state["kosis_trend_selection"] = (picked[0], picked[-1])
                st.rerun()

        sel = st.session_state.get("kosis_trend_selection")
        if sel:
            by_year = {r["연도"]: r for r in trend}
            start_y, end_y = sel
            if start_y in by_year and end_y in by_year:
                start_val = by_year[start_y]["매출액"] / 1_000_000
                end_val = by_year[end_y]["매출액"] / 1_000_000
                diff = end_val - start_val
                pct = diff / start_val * 100
                is_up = pct >= 0
                css_cls = "open" if is_up else "close"
                arrow = "▲" if is_up else "▼"
                st.markdown(
                    f'<div class="ov-stat {css_cls}" style="margin-top:12px; padding:18px 20px;">'
                    f'<div class="label">{start_y}년 대비 {end_y}년 총매출 변화</div>'
                    f'<div class="value" style="font-size:2.1rem;">{arrow} {abs(pct):.1f}%</div>'
                    f'<div class="delta" style="font-size:.88rem; margin-top:6px;">'
                    f'변화량 {diff:+.1f}조원 · {start_y}년 {start_val:.1f}조원 → {end_y}년 {end_val:.1f}조원</div>'
                    f'<div class="delta" style="margin-top:4px; font-style:italic;">'
                    f'"{start_y}년 대비 {end_y}년: 매출 {start_val:.1f}조원 → {end_val:.1f}조원 ({pct:+.1f}%)"</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if st.button("선택 해제", key="kosis_trend_reset"):
                st.session_state["kosis_trend_selection"] = None
                st.rerun()

    with st.container(border=True):
        st.markdown('<div class="ov-panel-title">인력 구조 추이 · 성별·연령 (전국, 국세청 개인사업자 기준)</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="ov-panel-desc">고령층(60대 이상) 비중은 늘고 40대 이하 비중은 줄어드는 추세 · 여성 비중은 꾸준히 증가</div>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div style="font-size:.82rem; color:{MUTED}; margin-bottom:4px;">연령대별 비중</div>', unsafe_allow_html=True)
            st.plotly_chart(_age_stack_chart(ims.tasis_age_trend()), use_container_width=True, config={"displayModeBar": False})
        with c2:
            st.markdown(f'<div style="font-size:.82rem; color:{MUTED}; margin-bottom:4px;">성별 비중</div>', unsafe_allow_html=True)
            st.plotly_chart(_gender_line_chart(ims.tasis_gender_trend()), use_container_width=True, config={"displayModeBar": False})

    with st.expander("연도별 원본 수치 보기", expanded=True):
        df = pd.DataFrame(trend)[["연도", "사업체수", "종사자수", "매출액", "영업비용", "인건비", "임차료", "기타경비", "급여총액", "평균매출_만원", "영업이익_만원"]]
        df.columns = ["연도", "사업체수", "종사자수", "매출액", "영업비용", "인건비", "임차료", "기타경비", "급여총액", "평균매출(만원)", "업체당 영업이익(만원)"]
        for col in df.columns:
            if col != "연도":
                df[col] = df[col].apply(lambda v: f"{v:,}" if pd.notna(v) else "–")
        st.caption("단위: 백만원 (사업체수·종사자수 제외, 평균매출은 만원)")
        st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("출처: 통계청 - 68221 (부동산 중개 및 대리업)")


def _render_tasis_tab():
    """탭1: 지역별 현황 — 개인사업자(공인중개사무소) 종합소득세 신고 기준, 시/도·시/군/구 드릴다운."""
    st.markdown(
        f'<div style="text-align:right; color:{MUTED}; font-size:.8rem;">개인사업자 · 2021~2025년 · 국세청 국세통계포털(TASIS) 기준'
        f'<br>평균 매출은 작년도 귀속(종합소득세 신고) 기준</div>',
        unsafe_allow_html=True,
    )
    years = ims.tasis_years()
    st.session_state.setdefault("industry_year", years[-1])
    year = st.selectbox(
        "기준연도", years, key="industry_year",
        format_func=lambda y: f"{y}년 ({int(y)-1}년 귀속 매출)",
    )

    drill = st.session_state.get("industry_drill_sido")

    if drill:
        rows = ims.tasis_district_snapshot(drill, year)
        bounds = ims.tasis_district_bounds(drill)
        map_title = f"{drill} 시/군/구별 부동산중개업 평균 연매출"
        rank_title = f"{drill} 시/군/구 순위"
        table_label = "시/군/구별 상세 표 보기"
        id_col = "시군구"
        b1, b2 = st.columns([0.14, 0.86])
        with b1:
            if st.button("← 전체보기", key="industry_drill_back", use_container_width=True):
                st.session_state["industry_drill_sido"] = None
                st.rerun()
        with b2:
            st.markdown(f'<div style="padding-top:8px; color:{MUTED}; font-size:.85rem;">전국 &gt; {drill}</div>', unsafe_allow_html=True)
    else:
        rows = ims.tasis_sido_snapshot(year)
        bounds = {"lat_range": None, "lon_range": None}
        map_title = "시/도별 부동산중개업 평균 연매출"
        rank_title = "지역별 순위"
        table_label = "시/도별 상세 표 보기"
        id_col = "지역"

    col_map, col_rank = st.columns([1.5, 1])
    with col_map:
        with st.container(border=True):
            st.markdown(f'<div class="ov-panel-title">{map_title}</div>', unsafe_allow_html=True)
            desc = "원 크기 = 평균 연매출" + ("" if drill else " · 원을 클릭하면 시/군/구로 확대됩니다(세종 제외)")
            st.markdown(f'<div class="ov-panel-desc">{desc}</div>', unsafe_allow_html=True)
            event = st.plotly_chart(
                _regional_map(rows, bounds["lat_range"], bounds["lon_range"]),
                use_container_width=True, config={"displayModeBar": False},
                on_select="rerun", selection_mode="points",
                key=f"industry_map_chart_{drill or 'root'}",
            )
            if not drill and event and event["selection"]["points"]:
                # 지도엔 배경 choropleth(전국 시/도 폴리곤)와 그 위의 버블(scattergeo) 두 트레이스가
                # 겹쳐 있다. 버블을 눌러도 그 밑 choropleth 폴리곤이 같이 선택되면서 points[0]가
                # customdata 없는 choropleth 쪽 포인트가 돼버려, 클릭이 무시되던(=드릴다운 실패 =
                # 그대로 전국에 머무는) 게 실제 버그였다. customdata가 있는 포인트를 찾아서 쓴다.
                clicked = None
                for p in event["selection"]["points"]:
                    cd = p.get("customdata")
                    if isinstance(cd, (list, tuple)):
                        cd = cd[0] if cd else None
                    if cd:
                        clicked = cd
                        break
                if clicked and ims.tasis_has_district(clicked):
                    st.session_state["industry_drill_sido"] = clicked
                    st.rerun()
                elif clicked:
                    st.info(f"'{clicked}'는 하위 시/군/구가 없어 더 확대할 수 없습니다.")
    national_row = ims.tasis_national(year)
    with col_rank:
        with st.container(border=True):
            st.markdown(f'<div class="ov-panel-title">{rank_title}</div>', unsafe_allow_html=True)
            st.markdown('<div class="ov-panel-desc">평균 연매출(만원) 기준 · 점선은 전국 평균</div>', unsafe_allow_html=True)
            st.plotly_chart(
                _regional_rank_chart(rows, national_avg=national_row["평균연매출"]),
                use_container_width=True, config={"displayModeBar": False},
            )

    with st.container(border=True):
        if drill:
            trend_title = f"{drill} 시/군/구별 평균 연매출 추이 (2021~2025)"
            trend_data = ims.tasis_district_trend(drill)
            trend_pin = None
        else:
            trend_title = "시/도별 평균 연매출 추이 (2021~2025)"
            trend_data = ims.tasis_sido_trend(include_national=True)
            trend_pin = "전국"
        title_col, toggle_col = st.columns([0.7, 0.3])
        with title_col:
            st.markdown(f'<div class="ov-panel-title">{trend_title}</div>', unsafe_allow_html=True)
        with toggle_col:
            chart_mode = st.segmented_control(
                "보기 방식", ["히트맵", "라인차트"], default="히트맵",
                key="industry_trend_chart_mode", label_visibility="collapsed",
            )
        if chart_mode == "라인차트":
            st.markdown('<div class="ov-panel-desc">선 = 지역별 궤적 · 굵은 검정선은 전국</div>', unsafe_allow_html=True)
            st.plotly_chart(
                _trend_line_chart(trend_data, pin_first=trend_pin),
                use_container_width=True, config={"displayModeBar": False},
            )
        else:
            st.markdown('<div class="ov-panel-desc">최신 연도 매출 순으로 정렬 · 진할수록 평균 연매출이 높음</div>', unsafe_allow_html=True)
            st.plotly_chart(
                _trend_heatmap(trend_data, pin_first=trend_pin),
                use_container_width=True, config={"displayModeBar": False},
            )

    if _SHOW_TASIS_DETAIL_TABLE:
        with st.expander(table_label, expanded=True):
            if drill:
                df = pd.DataFrame(rows)[["시군구", "평균연매출", "매출전년대비", "사업자수", "사업자수전년대비", "평균존속연수"]]
            else:
                df = pd.DataFrame(ims.tasis_sido_snapshot(year, include_national=True))[["지역", "평균연매출", "매출전년대비", "사업자수", "사업자수전년대비", "평균존속연수"]]
            df.columns = [id_col, "평균연매출", "매출 전년대비(%)", "사업자수", "사업자수 전년말대비(%)", "평균 사업 존속연수"]
            df["평균연매출"] = df["평균연매출"].apply(lambda v: f"{v:,}")
            df["매출 전년대비(%)"] = df["매출 전년대비(%)"].apply(_fmt_pct)
            df["사업자수"] = df["사업자수"].apply(lambda v: f"{v:,}")
            df["사업자수 전년말대비(%)"] = df["사업자수 전년말대비(%)"].apply(_fmt_pct)
            st.caption("단위: 평균연매출은 만원, 사업자수는 명")
            st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("※ 출처: 국세청 국세통계포털 '통계로 보는 생활업종 > 부동산중개업'. 개인사업자 종합소득세 신고 총수입금액 기준")


def render():
    st.markdown(
        f'<div class="ov-topline"><h1 style="margin:0;">{auth.PAGE_INDUSTRY_TRENDS}</h1>'
        '<div class="sub">국세청 국세통계포털 · 통계청 서비스업조사</div></div>',
        unsafe_allow_html=True,
    )

    tab_national, tab_tasis = st.tabs([
        "전국 시장 현황",
        "지역별 현황",
    ])

    with tab_national:
        _render_national_tab()

    with tab_tasis:
        _render_tasis_tab()
