# -*- coding: utf-8 -*-
"""
realtor(github pages) 대시보드에서 그대로 뽑아온 색상/폰트/여백 값.
https://hwshin0819.github.io/realtor/ 의 <style> 태그를 그대로 참고했다.
"""

GREEN = "#0E7A44"
GREEN_DEEP = "#0A5A33"
VERMILION = "#C64A2E"
BLUE = "#2563EB"
INK = "#1B231E"
PAPER = "#FFFFFF"
CARD = "#FFFFFF"
LINE = "#E2E6E1"
MUTED = "#6B756E"
ROW_HOVER = "#F6F9F5"
TABLE_LINE = "#EFF2EE"
ACCENT_SOFT = "#E3F0EA"

# 모던 SaaS(토스/노션 스타일) 룩: 페이지는 은은한 그레이, 그 위에 흰색 카드가 그림자로 떠 있는 형태
BG_PAGE = "#F8F9FA"
CARD_SHADOW = "0 1px 2px rgba(27,35,30,.04), 0 4px 14px rgba(27,35,30,.05)"

CSS = f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');

html, body, [class^="st-"], [class*=" st-"], .stApp, .stMarkdown, button, input, select, textarea {{
    font-family: "Pretendard Variable", Pretendard, -apple-system, "Malgun Gothic", sans-serif !important;
    font-variant-numeric: tabular-nums;
}}

/* Streamlit이 아이콘(화살표 등)에 쓰는 Material 아이콘 폰트는 그대로 살려둔다.
   (배경을 라이트로 바꿨으니 아이콘 색도 어둡게 다시 잡아준다) */
[data-testid="stIconMaterial"] {{
    font-family: "Material Symbols Rounded" !important;
    color: {MUTED} !important;
}}

.stApp {{
    background: {BG_PAGE};
    color: {INK};
}}

.block-container {{
    max-width: 1080px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}}

/* 헤더(상단 여백)도 페이지 배경과 통일 */
[data-testid="stHeader"] {{
    background: {BG_PAGE};
}}

/* 페이지 제목을 레퍼런스의 브랜드 텍스트 크기로 */
[data-testid="stAppViewContainer"] h1 {{
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    margin-bottom: 0 !important;
}}

section[data-testid="stSidebar"] {{
    background: {CARD};
    border-right: 1px solid {LINE};
    box-shadow: 1px 0 8px rgba(27,35,30,.03);
}}
section[data-testid="stSidebar"] * {{
    color: {INK} !important;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] button {{
    border-color: {LINE};
}}

h1, h2, h3 {{
    letter-spacing: -.02em;
    color: {INK};
}}

/* ── 버튼 (기본 = 아웃라인) ── */
div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button {{
    font-size: .83rem;
    font-weight: 500;
    border-radius: 10px;
    border: 1.5px solid {LINE};
    background: {CARD};
    color: {MUTED};
    padding: 7px 13px;
    transition: border-color .12s, color .12s, background .12s;
}}
div[data-testid="stButton"] button:hover,
div[data-testid="stFormSubmitButton"] button:hover {{
    border-color: {GREEN};
    color: {GREEN_DEEP};
    background: {CARD};
}}
div[data-testid="stButton"] button:focus:not(:active),
div[data-testid="stFormSubmitButton"] button:focus:not(:active) {{
    border-color: {GREEN};
    color: {GREEN_DEEP};
}}

/* primary 타입 버튼(저장/추가 등 핵심 액션)은 채워진 초록 버튼으로, 다운로드 버튼과 톤을 맞춘다 */
div[data-testid="stButton"] button[kind="primary"],
div[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stBaseButton-primary"] {{
    border: 1.5px solid {GREEN} !important;
    background: {GREEN} !important;
    color: #fff !important;
}}
div[data-testid="stButton"] button[kind="primary"]:hover,
div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {{
    background: {GREEN_DEEP} !important;
    border-color: {GREEN_DEEP} !important;
    color: #fff !important;
}}

/* 다운로드 버튼은 채워진 초록 버튼으로 */
div[data-testid="stDownloadButton"] button {{
    font-size: .83rem;
    font-weight: 500;
    border-radius: 10px;
    border: 1.5px solid {GREEN};
    background: {GREEN};
    color: #fff;
}}
div[data-testid="stDownloadButton"] button:hover {{
    background: {GREEN_DEEP};
    border-color: {GREEN_DEEP};
    color: #fff;
}}

/* ── select (react-aria ComboBox 기반) ── */
[data-testid="stSelectbox"] label p {{
    font-size: .83rem !important;
    font-weight: 500 !important;
    color: {MUTED} !important;
}}
[data-testid="stSelectbox"] [role="group"] {{
    border: 1.5px solid {LINE} !important;
    border-radius: 8px !important;
    background: {CARD} !important;
    box-shadow: none !important;
}}
[data-testid="stSelectbox"] input {{
    font-size: .9rem !important;
    color: {INK} !important;
}}
[role="listbox"] [role="option"][aria-selected="true"] {{
    background: {GREEN} !important;
    color: #fff !important;
}}
[role="listbox"] [role="option"]:hover {{
    background: {ROW_HOVER} !important;
}}

/* ── 패널(카드) 역할을 하는 container(border=True) ── */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 12px !important;
    border: 1px solid {LINE} !important;
    background: {CARD} !important;
    box-shadow: {CARD_SHADOW} !important;
}}

/* 라디오를 chips 처럼 */
div[role="radiogroup"] {{
    gap: 6px !important;
}}
div[role="radiogroup"] > label {{
    border: 1.5px solid {LINE};
    padding: 5px 12px;
    border-radius: 8px;
    background: {CARD};
    font-size: .83rem;
}}
div[role="radiogroup"] > label:has(input:checked) {{
    background: {GREEN};
    border-color: {GREEN};
}}
div[role="radiogroup"] > label:has(input:checked) p {{
    color: #fff !important;
}}
div[role="radiogroup"] input {{ display:none; }}

/* 사이드바 메뉴(왼쪽 페이지 네비게이션): 배경 강조 없이, 선택된 항목만 굵게 */
section[data-testid="stSidebar"] div[role="radiogroup"] {{
    flex-direction: column;
    gap: 2px !important;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] > label {{
    border: none;
    border-radius: 10px;
    padding: 10px 12px;
    background: transparent;
    font-size: 1.05rem;
    width: 100%;
}}
/* 라디오 동그라미 표시는 안 보이게 (아이콘/체크 표시 없이 텍스트만) */
section[data-testid="stSidebar"] div[role="radiogroup"] label div:has(+ [data-testid="stMarkdownContainer"]) {{
    display: none;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {{
    color: {INK} !important;
    font-weight: 700;
}}

/* 월별/분기별 같은 단순 단위 토글: 동그라미·색상 없는 얇은 버튼 형태 */
.st-key-ov_unit_toggle div[role="radiogroup"] > label {{
    background: {CARD};
    border-color: {LINE};
}}
.st-key-ov_unit_toggle div[role="radiogroup"] label div:has(+ [data-testid="stMarkdownContainer"]) {{
    display: none;
}}
.st-key-ov_unit_toggle div[role="radiogroup"] > label:has(input:checked) {{
    background: {CARD};
    border-color: {INK};
}}
.st-key-ov_unit_toggle div[role="radiogroup"] > label:has(input:checked) p {{
    color: {INK} !important;
    font-weight: 700;
}}

.ov-panel-title {{ font-size:1.02rem; font-weight:700; margin-bottom:2px; }}
.ov-panel-desc {{ font-size:.82rem; color:{MUTED}; margin-bottom:10px; }}

hr {{
    border-color: {LINE};
}}

/* ── 탭(st.tabs): 밑줄 하나로 깔끔하게, 선택된 탭만 굵게+초록 ── */
[role="tablist"] {{
    gap: 22px !important;
    border-bottom: 1.5px solid {LINE} !important;
}}
[data-testid="stTab"] {{
    padding: 6px 2px !important;
    font-size: .88rem !important;
    font-weight: 500 !important;
    color: {MUTED} !important;
}}
[data-testid="stTab"] p {{
    font-size: .88rem !important;
    font-weight: 500 !important;
    color: {MUTED} !important;
}}
[data-testid="stTab"][aria-selected="true"] {{
    color: {GREEN_DEEP} !important;
}}
[data-testid="stTab"][aria-selected="true"] p {{
    color: {GREEN_DEEP} !important;
    font-weight: 700 !important;
}}
.react-aria-SelectionIndicator {{
    background-color: {GREEN} !important;
    height: 2.5px !important;
}}

/* ── 커스텀 스탯 카드 (raw HTML) ── */
.ov-stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin: 4px 0 20px; }}
@media (max-width:900px) {{ .ov-stats {{ grid-template-columns:repeat(2,1fr); }} }}
.ov-stat {{ background:{CARD}; border:1px solid {LINE}; border-radius:12px; padding:15px 17px; box-shadow:{CARD_SHADOW}; }}
.ov-stat .label {{ font-size:.79rem; color:{MUTED}; font-weight:500; }}
.ov-stat .value {{ font-size:1.75rem; font-weight:700; letter-spacing:-.02em; margin-top:2px; }}
.ov-stat .delta {{ font-size:.75rem; color:{MUTED}; margin-top:2px; }}
.ov-stat.open .value {{ color:{GREEN}; }}
.ov-stat.close .value {{ color:{VERMILION}; }}
.ov-stat.net .value.plus {{ color:{GREEN}; }}
.ov-stat.net .value.minus {{ color:{VERMILION}; }}

/* ── 헤더 정보줄 ── */
.ov-topline {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom:18px; }}
.ov-topline .sub {{ font-size:.83rem; color:{MUTED}; }}
.ov-topline .updated {{ margin-left:auto; font-size:.78rem; color:{MUTED}; }}

/* ── 상세표 ── */
.ov-table-scroll {{ overflow-x:auto; margin:0 -4px; padding:0 4px; }}
.ov-table {{ border-collapse:collapse; font-size:.82rem; white-space:nowrap; width:100%; }}
.ov-table thead th {{ font-weight:500; color:{MUTED}; padding:6px 10px; border-bottom:1.5px solid {LINE}; text-align:right; }}
.ov-table thead th.mo {{ text-align:center; color:{INK}; }}
.ov-table thead th.oc-o {{ color:{GREEN}; }}
.ov-table thead th.oc-c {{ color:{VERMILION}; }}
.ov-table tbody td {{ padding:6px 10px; border-bottom:1px solid {TABLE_LINE}; text-align:right; }}
.ov-table tbody tr:hover {{ background:{ROW_HOVER}; }}
.ov-table td.net-up {{ background:{ACCENT_SOFT}; color:{GREEN_DEEP}; font-weight:600; }}
.ov-table td.net-down {{ background:#FBEAEA; color:{VERMILION}; font-weight:600; }}
.ov-table td.region, .ov-table th.region {{
    text-align:left; position:sticky; left:0; background:{CARD}; font-weight:500;
    border-right:1.5px solid {LINE};
}}
.ov-table tbody tr:hover td.region {{ background:{ROW_HOVER}; }}
.ov-table .bf {{ color:{MUTED}; }}
.ov-footnote {{ margin-top:6px; font-size:.77rem; color:{MUTED}; line-height:1.7; }}

/* ── 전국 상세표: 시/도 행 클릭 -> 시군구 행 펼치기/접기 ── */
.ov-table tr.region-toggle {{ cursor:pointer; }}
.ov-table tr.region-toggle:hover td {{ background:{ROW_HOVER}; }}
.ov-table .chev {{ display:inline-block; width:11px; color:{MUTED}; font-size:.7rem; }}
.ov-table td.district-cell {{ padding-left:28px; color:{MUTED}; font-weight:400; }}

/* ── 공헌이익 calculator 전용 표/뱃지 ── */
.calc-table-scroll {{ overflow-x:auto; margin:0 -4px; padding:0 4px; }}
.calc-table {{ border-collapse:collapse; font-size:.82rem; white-space:nowrap; width:100%; }}
.calc-table thead th {{ font-weight:500; color:{MUTED}; padding:6px 10px; border-bottom:1.5px solid {LINE}; text-align:right; }}
.calc-table thead th:first-child, .calc-table thead th:nth-child(2) {{ text-align:left; }}
.calc-table tbody td {{ padding:6px 10px; border-bottom:1px solid {TABLE_LINE}; text-align:right; font-variant-numeric:tabular-nums; }}
.calc-table tbody tr:hover {{ background:{ROW_HOVER}; }}
.calc-table td.region-cell {{ text-align:left; font-weight:600; vertical-align:middle; }}
.calc-table td.region-cell .disc {{ display:block; font-size:.72rem; color:{GREEN_DEEP}; margin-top:2px; font-weight:500; }}
.calc-table td.product-cell {{ text-align:left; font-weight:600; }}
.calc-compare {{ display:flex; align-items:baseline; justify-content:flex-end; gap:5px; }}
.calc-compare .was {{ color:{MUTED}; text-decoration:line-through; font-size:.72rem; font-weight:400; }}
.calc-compare .arrow {{ color:{MUTED}; font-size:.72rem; }}
.calc-compare .now.up {{ color:{VERMILION}; font-weight:600; }}
.calc-compare .now.down {{ color:{GREEN}; font-weight:600; }}
.calc-pill {{ display:inline-flex; align-items:center; padding:3px 9px; border-radius:99px; font-weight:700; font-size:.72rem; }}
.calc-pill.pass {{ background:{ACCENT_SOFT}; color:{GREEN}; }}
.calc-pill.fail {{ background:#FBEAEA; color:{VERMILION}; }}
.calc-grid-cell {{ font-weight:700; text-align:center; }}
.calc-grid-cell.good {{ color:{GREEN}; }}
.calc-grid-cell.bad {{ color:{VERMILION}; }}
.calc-hint {{ font-size:.78rem; color:{MUTED}; margin-top:2px; }}
</style>
"""


def inject():
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
