# -*- coding: utf-8 -*-
"""CP 현황: 네이버 부동산 CP(콘텐츠 제공사) 21개사의 회원수·매물수 점유율과
검증방식·지역 구조를 보는 메뉴. 집계는 cp_stats.py가 하고 여기선 그리기만 한다.

화면 전체가 상단 컨트롤(CP / 보기 / 시점·기간 / 한공협 포함)에 종속된다. 그 상태는 _period()가
만드는 T 하나로 모든 섹션에 전달된다.

'기간' 보기는 구간 합계가 아니라 '시작→끝 변화'로 해석한다 — 회원수·매물수가 그 시점의 스냅샷
(스톡)이라 여러 시점을 더하면 아무 의미가 없기 때문이다. 그래서 기간을 골라도 지역·검증방식 같은
스냅샷 표는 끝 시점 값을 보여주고, 바뀌는 건 증감의 기준(직전 시점 -> 구간 시작)과 추이 차트의
음영·지수 기준, 이슈 감지 범위다.

숫자를 읽을 때 반드시 알아야 하는 함정은 cp_stats.py 상단 주석과 '데이터 주의사항' 섹션에 있다.
"""
import io
import json
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import auth
import cp_stats as cs
import industry_market_stats as ims  # 시/도 GeoJSON 경로만 빌려 쓴다(중개업 시장 동향과 공용)
import region_utils as ru            # 시/도 중심 좌표(라벨 위치)도 그쪽과 공용
from theme import ACCENT_SOFT, CARD, GREEN, GREEN_DEEP, INK, LINE, MUTED, VERMILION

# geojson 피처의 code(행정구역코드 앞 2자리) <-> cp_stats가 쓰는 시/도 짧은 이름.
# industry_trends.py가 쓰는 것과 같은 파일(data/korea_sido.geojson, KOSTAT 코드)이라
# 매핑도 고정값이다 — 이 파일이 바뀔 일은 없다.
SIDO_CODE = {
    "서울": "11", "부산": "21", "대구": "22", "인천": "23", "광주": "24", "대전": "25",
    "울산": "26", "세종": "29", "경기": "31", "강원": "32", "충북": "33", "충남": "34",
    "전북": "35", "전남": "36", "경북": "37", "경남": "38", "제주": "39",
}

# 계열 색은 '항목'에 고정한다 — 순위가 바뀌어도 색이 따라 움직이면 추이를 잘못 읽게 된다.
SERIES_COLORS = {
    "이실장": "#2a78d6",
    "매경": "#eb6834",
    "써브": "#1baf7a",
    "뱅크": "#eda100",
}
COLOR_OTHER = "#e87ba4"   # 위 4개에 없는 '선택한 CP'
COLOR_HG = "#9AA4A0"      # 한공협(협회라 성격이 달라 회색 고정)
COLOR_ETC = "#C4CAC6"     # 상위권 밖을 묶은 '기타'
PILL_GREEN = "#027A48"    # 세그먼트 버튼 선택 상태 (실거래량 동향과 같은 배색 지침)

# 검증방식처럼 여러 계열을 한 그림에 쌓을 때 쓰는 순서 고정 팔레트.
# (dataviz 기준 팔레트 슬롯 1~8 — 인접쌍 CVD ΔE 9.1 / 일반시야 19.6으로 검증 통과.
#  대비 경고가 있는 슬롯이 있어 '막대 안 숫자 라벨 + 표 병기'를 반드시 함께 쓴다.)
# 순서는 고정이고 절대 돌려 쓰지 않는다 — 넘치는 항목은 색을 새로 만들지 않고 회색으로 둔다.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
           "#4a3aa7", "#e34948"]

# CP를 하나 고르는 대신 전 CP를 나란히 비교하는 모드.
ALL = "CP사 전체"

# 지역 히트맵의 검증방식 선택지. 화면에 쓰는 이름이 원자료 컬럼명과 달라 여기서 잇는다.
# 값이 여러 개면 합산(SUM)한다 — '로켓 타겟'이 그 경우다.
# 표시 순서가 곧 드롭다운 순서이고, 첫 항목이 기본 선택값이다.
HEATMAP_METRICS = {
    "집주인 방식": ["신홍보확인서", "모바일", "모바일v2"],
    "모바일 확인": ["모바일"],
    "모바일 확인2": ["모바일v2"],
    "(신) 홍보확인서": ["신홍보확인서"],
    # 홍보확인서와 홍보확인서2는 묶어서 '구홍보확인서' 하나로 본다.
    # (cs.DERIVED의 '구홍보전화'와는 다르다 — 그쪽은 전화확인까지 더한 값이다.)
    "(구) 홍보확인서": ["홍보확인서", "홍보확인서2"],
    "현장확인": ["현장확인"],
    "현장확인V2": ["현장확인v2"],
}
HM_KEY = "cp_hm_metric"
# 드롭다운에만 구성 방식을 풀어서 보여준다. 표 머리글·파일명까지 길어지면 읽기 어려워
# 실제 값은 짧은 이름을 쓰고, 표시만 format_func으로 바꾼다.
HM_LABEL = {"집주인 방식": "집주인 방식 (모바일확인+신홍보확인서)"}


def _hm_metric():
    """지역 히트맵의 기준 지표. 위젯이 히트맵 헤더에 있어서(=화면 아래쪽) 그보다 먼저 그리는
    시도별 표도 같은 값을 쓰도록 session_state에서 미리 읽는다. 값이 바뀌면 Streamlit이
    다시 실행하면서 session_state를 먼저 갱신하므로 두 섹션이 어긋나지 않는다."""
    v = st.session_state.get(HM_KEY)
    return v if v in HEATMAP_METRICS else next(iter(HEATMAP_METRICS))
# 한 그림에 색으로 구분해 올릴 계열 수 상한. 넘어가면 '기타'로 묶는다
# (색을 임의로 더 만들면 서로 구분이 안 돼 오히려 못 읽는다).
MAX_SERIES = 7

# 지역(어디) 축과 구성(무엇) 축을 탭으로 분리한다 — 기타는 전체 CP 이슈 목록이라
# 개별 CP를 볼 땐 의미가 없어 그 경우만 목록에서 뺀다(render()에서 동적으로 구성).
SECTIONS = ["시장 점유율", "검증 방식", "구성 비교"]
SECTION_ETC = "특이사항"

# 검증방식 묶음 — CP별 매물 검증방식 구성 차트 위 '전체 방식/집주인 방식' 토글과
# _share_table의 집주인 방식 소계가 같이 쓴다.
METHOD_SETS = {"전체 방식": None, "집주인 방식": ["모바일v2", "모바일", "신홍보확인서"]}


def _rule(top=28, bottom=14):
    """섹션을 한 탭에 이어 붙일 때 쓰는 구분선."""
    st.markdown(
        f'<hr style="border:none; border-top:1px solid {LINE}; '
        f'margin:{top}px 0 {bottom}px;">', unsafe_allow_html=True)

_EXTRA_CSS = f"""
<style>
/* KPI 5장 — 기본 .ov-stats는 4열이라 이 페이지에서만 5열로 */
.st-key-cp_root .ov-stats {{ grid-template-columns:repeat(5,1fr); }}
@media (max-width:1100px) {{ .st-key-cp_root .ov-stats {{ grid-template-columns:repeat(3,1fr); }} }}
@media (max-width:700px)  {{ .st-key-cp_root .ov-stats {{ grid-template-columns:repeat(2,1fr); }} }}
.st-key-cp_root .ov-stat .value {{ font-size:1.5rem; }}
.st-key-cp_root .ov-stat .sub {{ font-size:.72rem; color:{MUTED}; margin-top:3px; }}
.st-key-cp_root .up {{ color:{GREEN}; font-weight:600; }}
.st-key-cp_root .down {{ color:{VERMILION}; font-weight:600; }}

/* 표에서 '자사' 행을 강조 */
.st-key-cp_root .ov-table tr.me td {{ background:{ACCENT_SOFT}; font-weight:600; }}
.st-key-cp_root .ov-table tr.me td.region {{ background:{ACCENT_SOFT}; }}
.st-key-cp_root .ov-table td.name, .st-key-cp_root .ov-table th.name {{ text-align:left; }}
.st-key-cp_root .ov-table td.dim {{ color:{MUTED}; }}
/* 데이터 막대 칸 안에서 건수 뒤에 붙는 비율 — 숫자와 구분되게 옅은 색+살짝 작게 */
.st-key-cp_root .ov-dbpct {{ color:{MUTED}; font-size:.88em; margin-left:5px; }}

/* 검증방식 드롭다운 — Streamlit 셀렉트박스는 기본 최소폭이 200px라, 지도를 옆 칸과
   좌우로 나눠서 폭이 좁아지면 칸을 넘어 옆(CP별 매물 검증방식 구성) 위로 겹쳐 보였다.
   칸 폭에 맞게 줄이고, 넘치는 글자는 말줄임표로 자른다. */
.st-key-cp_root .st-key-cp_hm_metric {{ width:100% !important; min-width:0 !important; }}
.st-key-cp_root .st-key-cp_hm_metric input {{ text-overflow:ellipsis; }}

/* 이슈 CP 카드 */
.st-key-cp_root .cp-issues {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
@media (max-width:900px) {{ .st-key-cp_root .cp-issues {{ grid-template-columns:repeat(1,1fr); }} }}
.st-key-cp_root .cp-issue {{
    border:1px solid {LINE}; border-radius:12px; padding:13px 15px; background:{CARD};
}}
.st-key-cp_root .cp-issue .tag {{
    display:inline-block; font-size:.68rem; font-weight:700; padding:2px 8px;
    border-radius:99px; margin-bottom:6px;
}}
.st-key-cp_root .cp-issue .tag.gone {{ background:#FBEAEA; color:{VERMILION}; }}
.st-key-cp_root .cp-issue .tag.grow {{ background:{ACCENT_SOFT}; color:{GREEN_DEEP}; }}
.st-key-cp_root .cp-issue .tag.jump {{ background:#FEF3E2; color:#B45309; }}
.st-key-cp_root .cp-issue .nm {{ font-size:.98rem; font-weight:700; }}
.st-key-cp_root .cp-issue .ds {{ font-size:.76rem; color:{MUTED}; line-height:1.55; margin-top:3px; }}
.st-key-cp_root .cp-issue .spark {{ margin-top:8px; }}

/* 제목 오른쪽에 붙는 보기 전환 토글은 오른쪽 끝으로.
   부모가 flex라서 width:100%를 같이 주지 않으면 내용 크기로 줄어들어 우측 정렬이 어긋난다. */
.st-key-cp_root .st-key-cp_rm_basis,
.st-key-cp_root .st-key-cp_zone_view,
.st-key-cp_root .st-key-cp_mix_view,
.st-key-cp_root .st-key-cp_t2_dl,
.st-key-cp_root .st-key-cp_m_dl,
.st-key-cp_root .st-key-cp_methods_scope {{
    display:flex; justify-content:flex-end; width:100%;
}}

/* 시도 > 시군구 드릴다운 — 하위 행은 기본으로 접혀 있고 체크박스로 펼친다 */
.st-key-cp_root #cpdrill tr.kid,
.st-key-cp_root #rgdrill tr.kid {{ display:none; }}
.st-key-cp_root #cpdrill .drill-cb,
.st-key-cp_root #rgdrill .drill-cb {{ display:none; }}
.st-key-cp_root #cpdrill .drill-lb,
.st-key-cp_root #rgdrill .drill-lb {{ cursor:pointer; display:inline-flex; gap:5px; align-items:center; }}
.st-key-cp_root #cpdrill .drill-cb:checked + .drill-lb .chev,
.st-key-cp_root #rgdrill .drill-cb:checked + .drill-lb .chev {{ transform:rotate(90deg); }}
.st-key-cp_root #cpdrill .chev,
.st-key-cp_root #rgdrill .chev {{
    display:inline-block; width:11px; color:{MUTED}; font-size:.7rem; transition:transform .12s;
}}
.st-key-cp_root #cpdrill tr.kid td.region,
.st-key-cp_root #rgdrill tr.kid td.region {{ padding-left:22px; font-weight:400; }}
.st-key-cp_root #cpdrill tr.sido td,
.st-key-cp_root #rgdrill tr.sido td {{ font-weight:600; }}

/* 지역별 검증 방식 표 — 매물수·건수·구성비·점유율은 가운데 정렬(시·도/시·군·구 이름 열은
   .name이 이미 왼쪽 정렬을 지키므로 제외). */
.st-key-cp_root #cpdrill th:not(.region):not(.name),
.st-key-cp_root #cpdrill td:not(.region):not(.name) {{ text-align:center; }}

/* 세그먼트 버튼 — 다른 메뉴(실거래량 동향 '빠른 선택')와 같은 모양으로 통일한다.
   선택된 것만 초록 배경+흰 글자, 나머지는 회색 테두리.
   높이 38px은 옆에 서는 셀렉트박스에 맞춘 값이다(기본 32px이면 밑단이 떠 보인다). */
.st-key-cp_root button[data-variant="segmented_control"] {{
    height:38px !important;
    border:1.5px solid {LINE} !important;
    background:{CARD} !important;
    border-radius:8px !important;
}}
.st-key-cp_root button[data-variant="segmented_control"] p {{
    color:{MUTED} !important; font-weight:500 !important;
}}
.st-key-cp_root button[data-variant="segmented_control"][data-selected="true"] {{
    background:{PILL_GREEN} !important; border-color:{PILL_GREEN} !important;
}}
.st-key-cp_root button[data-variant="segmented_control"][data-selected="true"] p {{
    color:#fff !important; font-weight:700 !important;
}}
/* 검증방식별 지역 히트맵/지도 위 버튼(점유율·건수·CP 내 비중, 엑셀 다운로드)과
   CP별 매물 검증방식 구성 위 버튼(전체 방식·집주인 방식) — 지도가 옆 칸과 좌우로
   나뉘며 좁아지자 버튼이 상대적으로 커 보였다. 넷 다 점유율 버튼 크기로 맞춘다
   (다른 곳의 38px 버튼과는 무관하게 이 네 위젯에만 적용). */
.st-key-cp_root .st-key-cp_rm_basis button[data-variant="segmented_control"],
.st-key-cp_root .st-key-cp_methods_scope button[data-variant="segmented_control"] {{
    height:30px !important;
}}
.st-key-cp_root .st-key-cp_rm_basis button[data-variant="segmented_control"] p,
.st-key-cp_root .st-key-cp_methods_scope button[data-variant="segmented_control"] p {{
    font-size:.76rem !important;
}}
/* 엑셀 다운로드 — 앱 전체 기본은 채워진 초록 버튼(theme.py)인데, CP 현황에서는
   점유율/건수/CP내비중 같은 흐린 회색 버튼들 사이에 있어 혼자 튀어 보였다.
   이 페이지 안의 엑셀 버튼만 그 옆 토글과 같은 크기·회색 테두리 스타일로 바꾼다. */
.st-key-cp_root div[data-testid="stDownloadButton"] button {{
    height:30px !important; padding:0 12px !important; font-size:.76rem !important;
    font-weight:500 !important; border-radius:8px !important;
    border:1.5px solid {LINE} !important; background:{CARD} !important; color:{MUTED} !important;
}}
.st-key-cp_root div[data-testid="stDownloadButton"] button:hover {{
    border-color:{MUTED} !important; color:{INK} !important; background:{CARD} !important;
}}
/* 토글은 위에 라벨 줄이 없어 혼자 27px 위로 떠 있었다. 옆 컨트롤과 중심을 맞춘다. */
.st-key-cp_root .st-key-cp_hg_user,
.st-key-cp_root .st-key-cp_hg_forced {{ margin-top:27px; }}

/* 검증방식 드롭다운은 너무 넓어지지 않게 */
.st-key-cp_root .st-key-{HM_KEY} {{ max-width:300px; min-width:200px; margin-left:auto; }}

.st-key-cp_root .cp-note {{ font-size:.83rem; line-height:1.75; }}
.st-key-cp_root .cp-note b {{ color:{INK}; }}
.st-key-cp_root .cp-note li {{ margin-bottom:9px; }}
</style>
"""

FONT = "Pretendard Variable, Pretendard, sans-serif"


# ── 작은 표시 유틸 ───────────────────────────────────────────────────────────
def _num(v, dec=0, dash="–"):
    if v is None:
        return dash
    return f"{v:,.{dec}f}"


def _databar(inner, pct, color):
    """구성비만큼 셀 배경에 옅은 막대를 깐다. 표와 별도로 막대 차트를 하나 더 그리면
    같은 '구성비' 숫자를 두 번 보여주는 셈이라, 차트를 없애고 표 한 칸에 합친다."""
    p = 0.0 if not pct else max(0.0, min(100.0, pct))
    return (f'<td style="background:linear-gradient(to right,{color}28 {p:.3f}%,'
            f'transparent {p:.3f}%)">{inner}</td>')


def _pct(v, dec=2, dash="–"):
    return dash if v is None else f"{v:,.{dec}f}%"


def _signed(v, dec=1, suffix="%"):
    if v is None:
        return '<span class="dim">–</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "dim")
    return f'<span class="{cls}">{v:+,.{dec}f}{suffix}</span>'


def _period(D, mode, sel_lab, rng):
    """화면 전체가 공유하는 시점 문맥.

    i   = 기준 시점. 회원수·매물수는 스톡(그 시점의 스냅샷)이라 기간 합계가 성립하지 않으므로,
          지역·검증방식처럼 '그때의 모습'을 보는 섹션은 늘 이 시점 하나를 쓴다.
    cmp = 증감을 잴 비교 시점. 시점 모드면 직전 시점, 기간 모드면 구간 시작.
    lo~hi = 구간. 추이 차트의 음영과 이슈 감지 범위에 쓴다.
    """
    if mode == "기간":
        lo, hi = (D["labels"].index(rng[0]), D["labels"].index(rng[1]))
        if lo > hi:
            lo, hi = hi, lo
        return {"i": hi, "cmp": lo if lo < hi else None, "lo": lo, "hi": hi, "range": True}
    i = D["labels"].index(sel_lab)
    return {"i": i, "cmp": i - 1 if i > 0 else None, "lo": i, "hi": i, "range": False}


def _cp_options(D):
    """CP 드롭다운 순서: CP사 전체 → 프롭티어(전체) → 이실장 → 매경 → 나머지는 회원 점유율 순.
    정렬 기준을 '선택한 시점'이 아니라 늘 마지막 시점으로 고정한 이유는, 시점을 바꿀 때마다
    드롭다운 항목이 뒤섞이면 고르기 힘들어지기 때문이다."""
    last = D["nm"] - 1
    rest = sorted((c for c in D["cps"] if c not in cs.PROPTIER_PARTS),
                  key=lambda c: -cs.nz(D["d"][c]["m"][last]))
    return [ALL, cs.PROPTIER] + list(cs.PROPTIER_PARTS) + rest


def _cp_label(name):
    return "프롭티어(전체)" if name == cs.PROPTIER else name


def _own(selected):
    """표 머리글에서 '자사' 자리에 들어갈 이름. 전체 모드면 시장 전체라 '전체'."""
    return "전체" if selected == ALL else selected


def _ranked_cps(D, i, include_hg, key="m"):
    """시점 i의 회원수(또는 매물수) 내림차순 CP 목록."""
    return sorted(cs.market_cps(D, include_hg), key=lambda c: -cs.nz(D["d"][c][key][i]))


def _all_colors(D, i, include_hg):
    """전체 모드에서 CP -> 색. 고정색 4사와 한공협은 늘 자기 색, 남은 슬롯은 상위 CP에
    큰 순서로 배정하고, 상한을 넘는 CP는 '기타'로 묶어 색을 새로 만들지 않는다."""
    ranked = [c for c in _ranked_cps(D, i, include_hg) if c != cs.HANGONG]
    top = ranked[:MAX_SERIES]
    free = [c for c in PALETTE if c not in SERIES_COLORS.values()]
    colors, k = {}, 0
    for c in top:
        if c in SERIES_COLORS:
            colors[c] = SERIES_COLORS[c]
        else:
            colors[c] = free[k] if k < len(free) else COLOR_ETC
            k += 1
    if include_hg:
        colors[cs.HANGONG] = COLOR_HG
    return colors, top, [c for c in ranked if c not in top]


def _eun(word: str) -> str:
    """받침 유무에 맞는 조사(은/는)를 붙인다. '한공협는' 같은 표기를 막으려고."""
    ch = word[-1]
    if "가" <= ch <= "힣":
        return word + ("은" if (ord(ch) - 0xAC00) % 28 else "는")
    return word + "는"


def _growth(cur, prev):
    """전월 대비 증감률(%). 이전 값이 없거나 0이면 None."""
    if cur is None or not prev:
        return None
    return (cur / prev - 1) * 100


def series_color(name: str, selected: str) -> str:
    if name == cs.HANGONG:
        return COLOR_HG
    if name in SERIES_COLORS:
        return SERIES_COLORS[name]
    return COLOR_OTHER if name == selected else MUTED


def _axis(maxv: float, ticks: int = 5):
    """0 기준 축의 눈금 간격을 1·2·2.5·5 x 10^k 로 반올림하고 (간격, 축 상단)을 돌려준다."""
    if not maxv or maxv <= 0:
        return 1, 1
    raw = maxv / ticks
    k = math.floor(math.log10(raw))
    base = 10 ** k
    step = 10 * base
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * base * (1 + 1e-9):
            step = m * base
            break
    return step, math.ceil(maxv / step) * step


def _sparkline(vals, color, w=150, h=30):
    """의존성 없이 직접 만드는 인라인 SVG 스파크라인. None은 선을 끊는다."""
    pts = [v for v in vals if v is not None]
    if not pts:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or (abs(hi) or 1)
    n = len(vals)
    pad = 3

    def xy(i, v):
        x = pad + (w - 2 * pad) * (i / max(n - 1, 1))
        y = h - pad - (h - 2 * pad) * ((v - lo) / span)
        return x, y

    segs, cur = [], []
    for i, v in enumerate(vals):
        if v is None:
            if len(cur) > 1:
                segs.append(cur)
            cur = []
        else:
            cur.append(xy(i, v))
    if len(cur) > 1:
        segs.append(cur)

    paths = "".join(
        '<path d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in s) + '" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>'
        for s in segs
    )
    last = next((xy(i, v) for i, v in reversed(list(enumerate(vals))) if v is not None), None)
    dot = f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="2.6" fill="{color}"/>' if last else ""
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-hidden="true">{paths}{dot}</svg>')


def _hbar(names, values, colors, labels, *, xtitle, height=None, xmax=None):
    """정렬된 가로 막대. 숫자는 막대 안에 넣는다 — 대비가 약한 슬롯이 있어
    (dataviz 검증의 contrast WARN) 직접 라벨이 식별의 보조 수단 역할을 한다."""
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker=dict(color=colors, line=dict(width=2, color=CARD)),
        text=labels, textposition="auto", insidetextanchor="end",
        textfont=dict(size=11), cliponaxis=False,
        hovertemplate="%{y} · %{x:,.2f}<extra></extra>",
    ))
    step, top = _axis(xmax or (max(values) if values else 1))
    fig.update_layout(
        xaxis=dict(range=[0, top], dtick=step, gridcolor=LINE, title=xtitle),
        yaxis=dict(autorange="reversed", showgrid=False),
        showlegend=False, bargap=0.25,
    )
    _base_layout(fig, height=height or (26 * len(names) + 90))
    fig.update_layout(hovermode="closest")
    return fig


def _cat_colors(n):
    """항목 n개에 줄 색. 팔레트를 넘치면 색을 새로 만들지 않고 회색으로 떨어뜨린다."""
    return [PALETTE[k] if k < len(PALETTE) else COLOR_ETC for k in range(n)]


def _stacked100(rows, cats, matrix, colors=None, *, height=None, highlight=None,
                cat_focus=None):
    """100% 누적 가로 막대. rows=세로축 이름, cats=쌓을 항목, matrix[row][cat]=값.
    각 행을 100%로 정규화해 '구성이 서로 어떻게 다른가'만 보이게 한다.

    highlight에 행 이름을 주면 그 행만 선명하게 두고 나머지는 흐리게 처리한다(포커스).
    cat_focus에 항목(cats) 이름 집합을 주면 그 항목들만 선명하게 두고 나머지 항목은
    통째로 흐리게 처리한다 — 두 포커스는 곱해져서 같이 적용된다. 예전엔 이 묶음 선택을
    차트 안 Plotly 버튼(updatemenus)으로 넣었는데, 범례랑 겹쳐 보이는 문제가 있었다.
    호출하는 쪽에서 진짜 Streamlit 토글로 받은 값을 여기 인자로 넘기는 편이 더 낫다.
    """
    fig = go.Figure()
    colors = colors or _cat_colors(len(cats))
    totals = [sum(cs.nz(v) for v in r) or 1 for r in matrix]
    focus = set(highlight or ())
    dim = bool(focus) and not focus.issuperset(rows)
    opac = [1.0 if (not dim or r in focus) else 0.25 for r in rows]
    tcol = ["#FFFFFF" if (not dim or r in focus) else MUTED for r in rows]
    cat_focus = set(cat_focus) if cat_focus else None

    for j, cat in enumerate(cats):
        pct = [cs.nz(matrix[r][j]) / totals[r] * 100 for r in range(len(rows))]
        cat_factor = 1.0 if (not cat_focus or cat in cat_focus) else 0.15
        trace_opac = [o * cat_factor for o in opac]
        fig.add_trace(go.Bar(
            x=pct, y=rows, orientation="h", name=cat,
            marker=dict(color=colors[j], opacity=trace_opac, line=dict(width=2, color=CARD)),
            text=[f"{p:.0f}%" for p in pct], textposition="inside",
            textfont=dict(size=10, color=tcol), insidetextanchor="middle",
            hovertemplate="%{y} · " + cat + " %{x:.1f}%<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        xaxis=dict(range=[0, 100], dtick=25, ticksuffix="%", gridcolor=LINE, title="구성비"),
        yaxis=dict(autorange="reversed", showgrid=False),
        uniformtext=dict(minsize=9, mode="hide"),
    )
    _base_layout(fig, height=height or (26 * len(rows) + 120))
    # Plotly는 누적 차트의 범례를 자동으로 reversed로 뒤집는다. 가로 누적에서는 그러면
    # 범례 순서와 막대가 쌓이는 왼->오 순서가 반대가 되므로 normal로 고정한다.
    fig.update_layout(hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                                  traceorder="normal", font=dict(size=10)))
    return fig


def _heatmap(rows, cols, z, *, unit="%", digits=2, suffix="", height=None,
             title=None, highlight=None):
    """단일 색상 순차 램프 히트맵(무지개 금지). 값이 클수록 진하다.

    digits/suffix는 칸 안 숫자 서식. 건수를 소수점까지 찍으면 '32,044.00'처럼
    읽기만 나빠지고, 비율은 %가 붙어야 무슨 값인지 바로 안다.

    highlight에 CP 이름 집합을 주면 그 행들을 맨 위로 올리고 굵게 표시한다 — CP를
    골라도 21행 중 어디가 자기 것인지 안 보이던 문제를 고친다(탭1·탭2 히트맵
    공용, 다른 다중 CP 시각화는 이미 강조가 있는데 여기 둘만 빠져 있었다).
    프롭티어(전체)를 고르면 이실장·매경 두 행이 같이 뜨므로 집합으로 받는다."""
    hset = set(highlight or ())
    if hset & set(rows):
        hit = [r for r in rows if r in hset]
        rest = [r for r in rows if r not in hset]
        idx = {r: k for k, r in enumerate(rows)}
        rows2 = hit + rest
        z = [z[idx[r]] for r in rows2]
        rows = rows2
    text = [[("–" if v is None else f"{v:,.{digits}f}{suffix}") for v in r]
            for r in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=rows, text=text, texttemplate="%{text}",
        colorscale=[[0, "#EAF3EE"], [1, GREEN_DEEP]], showscale=False,
        xgap=2, ygap=2, textfont=dict(size=9, color=INK),
        hovertemplate="%{y} · %{x}<br>%{z:,." + str(digits) + "f}" + unit
                      + "<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(side="top", showgrid=False, tickfont=dict(size=10)),
        yaxis=dict(autorange="reversed", showgrid=False, tickfont=dict(size=10)),
    )
    _base_layout(fig, height=height or (24 * len(rows) + 90))
    fig.update_layout(hovermode="closest", showlegend=False)
    if hset & set(rows):
        # Plotly의 축 tickfont는 행마다 다른 색을 못 준다(실측: color에 배열을 넣으면
        # ValueError) — 그래서 라벨을 굵게 하는 대신, 해당 행 전체를 테두리로 감싼다.
        # 맨 위로 이미 옮겨놨으니 index 0이 곧 그 행이다.
        fig.update_layout(shapes=[
            dict(type="rect", xref="paper", yref="y", x0=0, x1=1,
                 y0=k - 0.5, y1=k + 0.5,
                 line=dict(color=GREEN_DEEP, width=2), fillcolor="rgba(0,0,0,0)")
            for k, r in enumerate(rows) if r in hset
        ])
    return fig


@st.cache_data
def _load_sido_geo():
    with open(ims.geojson_path(), encoding="utf-8") as f:
        return json.load(f)


def _sido_choropleth(sidos, values, *, digits=2, suffix="%", height=480):
    """CP 한 곳의 지역별 분포를 21행 격자 대신 실제 시/도 지도로 보여준다 — 어디에
    쏠려 있는지 읽으려고 21개 CP 사이에서 한 줄을 찾을 필요가 없다.

    D["sidos"]는 항상 SIDO_CODE의 17개 키와 정확히 일치한다(cp_stats.SIDO_ORDER로
    고정) — 그래서 아래는 둘이 1:1이라고 가정하고 방어적 필터 없이 바로 dict로 짠다.

    시/군/구 단위 경계 데이터는 이 프로젝트에 없어(중개업 시장 동향도 시/도까지만
    쓴다) 시/도 17개 단위로 그린다. 값이 없는 시/도는 옅게 그대로 두되(0과는 다름),
    hover·라벨에는 '–'로 구분해 0과 결측을 헷갈리지 않게 한다."""
    geo = _load_sido_geo()
    codes = [f["properties"]["code"] for f in geo["features"]]
    code_to_sido = {v: k for k, v in SIDO_CODE.items()}
    val_of = {SIDO_CODE[s]: v for s, v in zip(sidos, values)}
    label_of = {s: (f"{s}<br>–" if v is None else f"{s}<br>{_num(v, digits)}{suffix}")
                for s, v in zip(sidos, values)}

    z = [val_of.get(c) for c in codes]
    zmax = max((v for v in z if v is not None), default=1)

    fig = go.Figure(go.Choropleth(
        geojson=geo, locations=codes, z=[v if v is not None else 0 for v in z],
        featureidkey="properties.code", zmin=0, zmax=zmax or 1,
        colorscale=[[0, "#EAF3EE"], [1, GREEN_DEEP]], showscale=False,
        marker_line_color=CARD, marker_line_width=1.5,
        text=[label_of.get(code_to_sido.get(c, ""), "") for c in codes],
        hovertemplate="%{text}<extra></extra>",
    ))

    fig.add_trace(go.Scattergeo(
        lon=[ru.SIDO_LATLON[s][1] for s in sidos], lat=[ru.SIDO_LATLON[s][0] for s in sidos],
        text=[label_of[s] for s in sidos], mode="text",
        textfont=dict(size=10, color=INK), hoverinfo="skip", showlegend=False,
    ))
    fig.update_geos(
        visible=False, showcountries=False, showcoastlines=False, showland=False,
        lataxis_range=[32.8, 38.8], lonaxis_range=[124.4, 131.0],
        projection_type="mercator", bgcolor=CARD,
    )
    fig.update_layout(paper_bgcolor=CARD, margin=dict(l=0, r=0, t=0, b=0), height=height)
    return fig


def _drill_frame(D, cps, i, scope, methods, live, tot_l):
    """검증방식 지역 표의 내보내기용 원본. 화면 표와 같은 (시도, 시군구) 행을 쓰되
    서식 없는 숫자로 건수·구성비·점유율을 함께 담는다."""
    df = cs.district_rows(D, cps, i, scope)
    if df.empty:
        return pd.DataFrame()
    out = df[["시도", "구시군", "매물수"]].copy()
    for j in live:
        col = methods[j] + "매물수"
        v = df[col]
        out[f"{methods[j]} 건수"] = v
        out[f"{methods[j]} 구성비(%)"] = (v / df["매물수"].replace(0, pd.NA) * 100).round(2)
        out[f"{methods[j]} 점유율(%)"] = (v / tot_l[j] * 100).round(2) if tot_l[j] else None
    # 가나다순이 아니라 화면과 같은 시도 순서(cs.SIDO_ORDER)로 내보낸다.
    order = {sd: k for k, sd in enumerate(D["sidos"])}
    out["_o"] = out["시도"].map(order).fillna(len(order))
    return (out.sort_values(["_o", "매물수"], ascending=[True, False])
               .drop(columns="_o"))


def _drill_table(D, cps, i, scope, methods, live, tot_l):
    """시도 > 시군구 계층 표. 시도 행을 누르면 그 아래 시군구 행이 펼쳐진다.

    st.markdown은 <script>를 지우기 때문에 JS 없이 CSS만으로 접었다 편다 —
    숨긴 체크박스 + :has() 선택자. 지원되지 않는 브라우저에서도 시도 행은 그대로 보이고
    시군구만 안 펼쳐지므로 표가 깨지지는 않는다.
    """
    df = cs.district_rows(D, cps, i, scope)
    if df.empty:
        return '<div class="ov-footnote">이 지역에 데이터가 없습니다.</div>'

    vcols = [methods[j] + "매물수" for j in live]
    names = [methods[j] for j in live]
    sido_g = df.groupby("시도", as_index=False)[["매물수"] + vcols].sum()
    order = {sd: k for k, sd in enumerate(D["sidos"])}
    sido_g = sido_g.sort_values("시도", key=lambda c: c.map(order).fillna(len(order)))

    def cells(row):
        base = row["매물수"] or 1
        out = ""
        for k, j in enumerate(live):
            v = row[vcols[k]]
            sh = (v / tot_l[j] * 100) if tot_l[j] else None
            out += (f'<td class="dim">{_num(v)}</td>'
                    f'<td>{_pct(v / base * 100, 1)}</td>'
                    f'<td>{_pct(sh, 2)}</td>')
        return f'<td>{_num(row["매물수"])}</td>' + out

    rules, body = [], ""
    for n, srow in enumerate(sido_g.itertuples(index=False)):
        sd = srow.시도
        kids = df[df["시도"] == sd].sort_values("매물수", ascending=False)
        gid = f"cpg{n}"
        has_kids = len(kids) > 0
        srow_d = dict(zip(sido_g.columns, srow))
        if has_kids:
            rules.append(f"#cpdrill:has(#{gid}:checked) tr.{gid}{{display:table-row;}}")
            label = (f'<input type="checkbox" id="{gid}" class="drill-cb">'
                     f'<label for="{gid}" class="drill-lb"><span class="chev">▸</span>{sd}</label>')
        else:
            label = sd
        body += (f'<tr class="sido"><td class="region name">{label}</td>'
                 f'<td class="dim">전체 {len(kids)}개</td>{cells(srow_d)}</tr>')
        for krow in kids.itertuples(index=False):
            kd = dict(zip(kids.columns, krow))
            body += (f'<tr class="{gid} kid"><td class="region name dim">{sd}</td>'
                     f'<td class="name">{kd["구시군"]}</td>{cells(kd)}</tr>')

    head = "".join(f'<th colspan="3">{n}</th>' for n in names)
    sub = "".join('<th class="dim">건수</th><th>구성비</th><th>점유율</th>' for _ in names)
    css = ("<style>" + "".join(rules) + "</style>") if rules else ""
    return (css + '<div class="ov-table-scroll"><table class="ov-table" id="cpdrill"><thead>'
            '<tr><th class="region name" rowspan="2">시·도</th>'
            f'<th class="name" rowspan="2">시·군·구</th><th rowspan="2">매물수</th>{head}</tr>'
            f"<tr>{sub}</tr></thead><tbody>{body}</tbody></table></div>")


def _xlsx(df, sheet="data"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet[:31])
    return buf.getvalue()


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _dl_button(df, stem, key, sheet="data"):
    """표 우측 상단에 붙는 엑셀 내려받기 버튼. 화면 표와 같은 값을 서식 없는 숫자로 넣는다."""
    st.download_button("엑셀 다운로드", _xlsx(df, sheet),
                       file_name=f"{stem}.xlsx", mime=XLSX_MIME, key=key)


def _region_drill_cols(lab):
    """선택한 CP 이름이 들어간 컬럼명. 표와 엑셀이 같은 이름을 쓰도록 한 곳에서 만든다."""
    return f"{lab} 매물수", f"{lab} 내 구성비(%)"


def _region_drill_frame(D, cps, mkt_cps, i, lab):
    """(권역, 시도, 시군구)별 선택 CP·시장 매물수. 화면 표와 엑셀이 같은 숫자를 쓴다."""
    own_c, mix_c = _region_drill_cols(lab)
    mine = cs.district_rows(D, cps, i, cs.NATION)[["시도", "구시군", "매물수"]]
    mkt = cs.district_rows(D, mkt_cps, i, cs.NATION)[["시도", "구시군", "매물수"]]
    df = mine.merge(mkt, on=["시도", "구시군"], how="outer",
                    suffixes=("_자사", "_시장")).fillna(0)
    df = df.rename(columns={"매물수_자사": own_c, "매물수_시장": "시장 매물수"})
    df["권역"] = df["시도"].map(lambda s: D["zone_of"].get(s, "지방"))
    tot = df[own_c].sum() or 1
    df[mix_c] = (df[own_c] / tot * 100).round(2)
    df["점유율(%)"] = [
        round(a / b * 100, 2) if b else None
        for a, b in zip(df[own_c], df["시장 매물수"])]
    order = {z: k for k, z in enumerate(D["zones"])}
    df = df.sort_values(["권역", own_c],
                        key=lambda c: c.map(order) if c.name == "권역" else -c)
    return df[["권역", "시도", "구시군", own_c, mix_c, "시장 매물수", "점유율(%)"]]


def _region_drill_html(D, df, lab):
    """권역 열 + 시도 행(클릭하면 시군구 펼침). CSS :has()로 JS 없이 접었다 편다."""
    own_c, mix_c = _region_drill_cols(lab)
    if df.empty:
        return '<div class="ov-footnote">이 시점에 표시할 지역이 없습니다.</div>'
    agg = (df.groupby(["권역", "시도"], as_index=False)
             [[own_c, mix_c, "시장 매물수"]].sum())
    zorder = {z: k for k, z in enumerate(D["zones"])}
    agg = agg.sort_values(["권역", own_c],
                          key=lambda c: c.map(zorder) if c.name == "권역" else -c)

    def cells(mine, mix, mkt):
        sh = (mine / mkt * 100) if mkt else None
        return (f"<td>{_num(mine)}</td><td>{_pct(mix, 2)}</td>"
                f'<td class="dim">{_num(mkt)}</td><td>{_pct(sh)}</td>')

    # 컬럼명에 공백·괄호가 있어 itertuples의 위치 기반 이름(_3 등)은 쓰지 않는다.
    rules, body = [], ""
    for n, row in enumerate(agg.to_dict("records")):
        kids = df[df["시도"] == row["시도"]].to_dict("records")
        gid = f"rz{n}"
        rules.append(f"#rgdrill:has(#{gid}:checked) tr.{gid}{{display:table-row;}}")
        label = (f'<input type="checkbox" id="{gid}" class="drill-cb">'
                 f'<label for="{gid}" class="drill-lb"><span class="chev">▸</span>'
                 f'{row["시도"]}</label>')
        body += (f'<tr class="sido"><td class="dim">{row["권역"]}</td>'
                 f'<td class="region name">{label}</td>'
                 + cells(row[own_c], row[mix_c], row["시장 매물수"])
                 + "</tr>")
        # 시·군·구는 별도 열 없이 부모 시·도 바로 아래에 들여써서 붙인다.
        for k in kids:
            body += (f'<tr class="{gid} kid"><td class="dim">{k["권역"]}</td>'
                     f'<td class="region name">{k["구시군"]}</td>'
                     + cells(k[own_c], k[mix_c], k["시장 매물수"])
                     + "</tr>")

    return ("<style>" + "".join(rules) + "</style>"
            '<div class="ov-table-scroll"><table class="ov-table" id="rgdrill"><thead><tr>'
            '<th>권역</th><th class="region name">시·도 · 시·군·구</th>'
            f'<th>{lab} 매물수</th><th>{lab} 내 구성비</th>'
            '<th>시장 매물수</th><th>점유율</th>'
            f"</tr></thead><tbody>{body}</tbody></table></div>")


def _base_layout(fig, height=380, ylab=None):
    fig.update_layout(
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family=FONT, color=INK, size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=11)),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=30, b=10),
        height=height, dragmode=False,
    )
    if ylab:
        fig.update_yaxes(title=ylab)
    return fig


# ── 섹션 2·3 ─────────────────────────────────────────────────────────────────



def _per_member_rank(D, selected, T, include_hg):
    """회원 1계약당 매물수 랭킹. 회원수가 CP 계약 건수라 '1인당'이 아니라 '1계약당'이다."""
    i = T["i"]
    st.markdown('<div class="ov-panel-title">회원당 매물수 (생산성)</div>',
                unsafe_allow_html=True)
    per = [(c, cs.per_member(D, c)[i]) for c in _ranked_cps(D, i, include_hg)]
    per = sorted([(c, v) for c, v in per if v is not None], key=lambda t: -t[1])
    if not per:
        st.info("이 시점에 계산할 수 있는 CP가 없습니다.")
        return
    colors, _, _ = _all_colors(D, i, include_hg)
    me = set(cs.PROPTIER_PARTS) if selected == cs.PROPTIER else {selected}
    st.plotly_chart(
        _hbar([c for c, _ in per], [v for _, v in per],
              [colors.get(c, series_color(c, selected) if c in me else COLOR_ETC)
               for c, _ in per],
              [f"{v:,.1f}건" for _, v in per], xtitle="회원 1계약당 매물수"),
        use_container_width=True, config={"displayModeBar": False})


# ── 섹션 4·5 ─────────────────────────────────────────────────────────────────
def _rank_rows(D, T, include_hg):
    sel_i, ci = T["i"], T["cmp"]
    rows = []
    for cp in cs.market_cps(D, include_hg):
        d = D["d"][cp]
        m, l = d["m"][sel_i], d["l"][sel_i]
        sh = cs.share_series(D, cp, "m", include_hg)
        first_m = next((v for v in d["m"] if v), None)
        rows.append({
            "cp": cp, "m": m, "l": l,
            "mom": _growth(m, d["m"][ci]) if ci is not None else None,
            "share": sh[sel_i],
            "dshare": None if (ci is None or sh[sel_i] is None or sh[ci] is None)
            else sh[sel_i] - sh[ci],
            "cum": _growth(m, first_m),
            "per": (l / m) if (m and l is not None) else None,
            "cover": cs.cover_series(D, cp)[sel_i],
        })
    rows.sort(key=lambda r: -(r["m"] or 0))
    return rows


def _section_rank(D, selected, T, include_hg):
    sel_i, ci = T["i"], T["cmp"]
    st.markdown('<div class="ov-panel-title">CP별 회원 점유율 및 매물 집계표</div>',
                unsafe_allow_html=True)

    rows = _rank_rows(D, T, include_hg)
    me = set(cs.PROPTIER_PARTS) if selected == cs.PROPTIER else {selected}

    body = ""
    if selected == cs.PROPTIER:
        d = D["d"][cs.PROPTIER]
        sh = cs.share_series(D, cs.PROPTIER, "m", include_hg)
        first_m = next((v for v in d["m"] if v), None)
        body += (
            f'<tr class="me"><td class="region name">합산 · {_cp_label(cs.PROPTIER)}</td>'
            f'<td>{_num(d["m"][sel_i])}</td>'
            f'<td>{_signed(_growth(d["m"][sel_i], d["m"][ci]) if ci is not None else None)}</td>'
            f'<td>{_pct(sh[sel_i])}</td>'
            f'<td>{_signed(None if ci is None or sh[sel_i] is None or sh[ci] is None else sh[sel_i]-sh[ci], 2, "%p")}</td>'
            f'<td>{_signed(_growth(d["m"][sel_i], first_m))}</td>'
            f'<td>{_num(d["l"][sel_i])}</td>'
            f'<td>{_num((d["l"][sel_i] / d["m"][sel_i]) if d["m"][sel_i] else None, 1)}</td>'
            f'<td class="dim">–</td></tr>')

    for i, r in enumerate(rows, 1):
        cls = ' class="me"' if r["cp"] in me else ""
        body += (
            f'<tr{cls}><td class="region name">{i}. {r["cp"]}</td>'
            f'<td>{_num(r["m"])}</td>'
            f'<td>{_signed(r["mom"])}</td>'
            f'<td>{_pct(r["share"])}</td>'
            f'<td>{_signed(r["dshare"], 2, "%p")}</td>'
            f'<td>{_signed(r["cum"])}</td>'
            f'<td>{_num(r["l"])}</td>'
            f'<td>{_num(r["per"], 1)}</td>'
            f'<td class="dim">{(_num(r["cover"], 2) + "배") if r["cover"] else "–"}</td></tr>')

    prev_lab = D["labels"][ci] if ci is not None else "–"
    st.markdown(
        '<div class="ov-table-scroll"><table class="ov-table"><thead><tr>'
        '<th class="region name">회사명</th><th>회원수</th>'
        f'<th>{prev_lab} 대비</th><th>회원 점유율</th><th>점유율Δ</th>'
        f'<th>{D["labels"][0]} 대비 누적</th><th>매물수</th><th>회원당 매물</th><th>커버 배수</th>'
        f"</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True)
    st.markdown(
        '<div class="ov-footnote">커버 배수 = 상세 행 회원수 합 ÷ 총계 회원수. '
        '1보다 클수록 한 회원이 여러 지역·매물유형에 걸쳐 중복 계상됐다는 뜻이라, '
        '이 값이 바로 “상세 회원수를 더하면 안 되는” 이유다. '
        '회원수가 0인 CP(퇴출)와 합산 행인 프롭티어는 정의되지 않아 – 로 둔다.</div>',
        unsafe_allow_html=True)


def _detect_issues(D, include_hg, lo, hi):
    """퇴출 / 추세 성장 / 급변을 lo~hi 구간 안에서만 판정한다. 회원수·매물수 둘 다 본다."""
    out = []
    span = list(range(lo, hi + 1))
    if len(span) < 2:
        return out
    for cp in cs.market_cps(D, include_hg):
        for key, lab, unit in (("m", "회원수", "명"), ("l", "매물수", "건")):
            full = D["d"][cp][key]
            v = [full[k] for k in span]
            labs = [D["labels"][k] for k in span]
            pts = [x for x in v if x is not None]
            if len(pts) < 2:
                continue
            first = next((x for x in v if x), None)
            last = v[-1]

            if last == 0 and first:
                li = max(i for i, x in enumerate(v) if x)
                out.append(dict(cp=cp, kind="gone", tag="퇴출", key=key,
                                desc=f"{lab}가 {labs[-1]}에 0. 마지막 관측은 "
                                     f"{labs[li]} ({_num(v[li])}{unit}), "
                                     f"최고는 {_num(max(pts))}{unit}.",
                                vals=v))
                break

            if first:
                chg = (last / first - 1) * 100
                steps = [(v[i], v[i - 1]) for i in range(1, len(v))
                         if v[i] is not None and v[i - 1] is not None]
                ups = sum(1 for a, b in steps if a >= b)
                if chg >= 15 and steps and ups / len(steps) >= 0.7:
                    out.append(dict(cp=cp, kind="grow", tag="추세 성장", key=key,
                                    desc=f"{lab} {_num(first)}{unit} → {_num(last)}{unit} "
                                         f"({chg:+.1f}%) · {len(steps)}개 구간 중 {ups}개가 상승.",
                                    vals=v))
                    continue

            worst, wi = 0, None
            for i in range(1, len(v)):
                g = _growth(v[i], v[i - 1])
                if g is not None and abs(g) > abs(worst):
                    worst, wi = g, i
            if wi is not None and abs(worst) >= 25:
                out.append(dict(cp=cp, kind="jump", tag="급변", key=key,
                                desc=f"{labs[wi-1]}→{labs[wi]} {lab}가 {worst:+.1f}% "
                                     f"({_num(v[wi-1])} → {_num(v[wi])}{unit}).",
                                vals=v))
    order = {"gone": 0, "jump": 1, "grow": 2}
    out.sort(key=lambda r: (order[r["kind"]], r["cp"]))
    return out


def _section_issues(D, selected, T, include_hg):
    # 시점 모드에선 전 기간을, 기간 모드에선 고른 구간만 본다.
    lo, hi = (T["lo"], T["hi"]) if T["range"] else (0, D["nm"] - 1)
    st.markdown('<div class="ov-panel-title">CP사별 이슈 현황</div>', unsafe_allow_html=True)

    issues = _detect_issues(D, include_hg, lo, hi)
    if not issues:
        st.info("이 구간에서 규칙에 걸리는 CP가 없습니다."
                + (" (시점을 2개 이상 포함해야 판정할 수 있습니다.)" if hi - lo < 1 else ""))
        return
    cards = ""
    for it in issues:
        color = series_color(it["cp"], selected)
        cards += (
            f'<div class="cp-issue"><span class="tag {it["kind"]}">{it["tag"]}</span>'
            f'<div class="nm">{it["cp"]}</div><div class="ds">{it["desc"]}</div>'
            f'<div class="spark">{_sparkline(it["vals"], color)}</div></div>')
    st.markdown(f'<div class="cp-issues">{cards}</div>', unsafe_allow_html=True)


# ── 섹션 6 ───────────────────────────────────────────────────────────────────


# ── 섹션 7 ───────────────────────────────────────────────────────────────────
def _methods_all_chart(D, T, include_hg, region, methods, live):
    """전체 모드 그래프 — 어느 CP가 어떤 검증방식에 기대고 있는지 100% 누적 막대로."""
    i = T["i"]
    names = [methods[j] for j in live]
    # 검증방식 자료가 아예 없는 CP(한공협)와 그 시점에 0건인 CP는 행에서 빠진다.
    cps, mat = [], []
    for c in _ranked_cps(D, i, include_hg, "l"):
        row = cs.method_vec(D, c, i, region)
        if row is None or all(v is None for v in row):
            continue
        vals = [cs.nz(row[j]) for j in live]
        if sum(vals) == 0:
            continue
        cps.append(c)
        mat.append(vals)
    if not cps:
        st.info("이 지역에 검증방식 데이터가 없습니다.")
        return
    # 예전엔 이 자리가 차트 안 Plotly 버튼이라 범례랑 겹쳐 보였다 — 지도 쪽 지표 토글과
    # 같은 모양의 진짜 Streamlit 버튼으로 바꿔서 범례 위, 차트 밖에 둔다.
    scope = st.segmented_control(
        "범위", ["전체 방식", "집주인 방식"], default="전체 방식",
        key="cp_methods_scope", label_visibility="collapsed") or "전체 방식"
    cat_focus = set(METHOD_SETS["집주인 방식"]) if scope == "집주인 방식" else None
    st.plotly_chart(_stacked100(cps, names, mat, cat_focus=cat_focus),
                    use_container_width=True, config={"displayModeBar": False})



def _region_methods_all(D, selected, T, include_hg, focus):
    """전체 모드: CP x 시도 히트맵 — 어느 CP가 어느 지역에 그 방식을 밀고 있는지.
    개별 CP 모드: 21행 격자에서 한 줄을 찾는 대신, 그 CP 하나의 지역별 분포를
    시/도 지도로 바로 보여준다(_sido_choropleth)."""
    i = T["i"]
    sidos = D["sidos"]
    idx = [D["methods"].index(p) for p in HEATMAP_METRICS[focus]]

    # 제목이 길어져서(검증방식별 지역 히트맵/지도) 한 줄에 드롭다운·지표까지 다 넣으면
    # 잘렸다 — 제목+검증방식 드롭다운을 한 줄, 지표 토글(오른쪽 정렬)을 그 아래 한 줄로
    # 나눈다. 엑셀 다운로드는 표시할 값이 화면과 같은 시·도 집계뿐이라 따로 없앴다.
    head_l, head_m = st.columns([2.0, 1.0])
    head_l.markdown(
        '<div class="ov-panel-title" style="padding-top:9px;">'
        + ("검증방식별 지역 히트맵" if selected == ALL else "검증방식별 지역 지도") + "</div>",
        unsafe_allow_html=True)
    with head_m:
        st.selectbox("검증방식", list(HEATMAP_METRICS), key=HM_KEY,
                     format_func=lambda k: HM_LABEL.get(k, k),
                     label_visibility="collapsed")
    _, head_r = st.columns([1.3, 1.7])
    with head_r:
        basis = st.segmented_control(
            "보기 지표", ["점유율", "건수", "CP 내 비중"], default="점유율",
            key="cp_rm_basis", label_visibility="collapsed") or "점유율"

    mkt = []
    for sd in sidos:
        s = 0
        for c in cs.market_cps(D, include_hg):
            row = cs.method_vec(D, c, i, sd)
            s += sum(cs.nz(row[j]) for j in idx)
        mkt.append(s)

    def raw_count(cp, sd):
        row = cs.method_vec(D, cp, i, sd)
        raw = [row[j] for j in idx]
        return None if all(v is None for v in raw) else sum(cs.nz(x) for x in raw)

    # 건수는 정수, 비율은 %. 점유율은 작은 값(0.5% 등)이 많아 두 자리를 남긴다.
    fmt = ({"unit": "", "digits": 0, "suffix": ""} if basis == "건수"
           else {"unit": "%", "digits": 2, "suffix": "%"} if basis == "점유율"
           else {"unit": "%", "digits": 1, "suffix": "%"})

    if selected == ALL:
        rows, z = [], []
        for cp in _ranked_cps(D, i, include_hg, "l"):
            vals, any_data = [], False
            for k, sd in enumerate(sidos):
                v = raw_count(cp, sd)
                if v is None:
                    vals.append(None)
                    continue
                any_data = True
                if basis == "건수":
                    vals.append(v)
                elif basis == "점유율":
                    vals.append((v / mkt[k] * 100) if mkt[k] else None)
                else:
                    own = cs.listings_at(D, cp, i, sd)
                    vals.append((v / own * 100) if own else None)
            if any_data and any(cs.nz(v) for v in vals):
                rows.append(cp)
                z.append(vals)

        st.plotly_chart(_heatmap(rows, sidos, z, **fmt),
                        use_container_width=True, config={"displayModeBar": False})
        return

    # 개별 CP(또는 프롭티어 합산) — 시/도별 값을 하나만 뽑아 지도로 그린다.
    mine_cps = list(cs.PROPTIER_PARTS) if selected == cs.PROPTIER else [selected]
    vals = []
    for k, sd in enumerate(sidos):
        counts = [raw_count(cp, sd) for cp in mine_cps]
        if all(c is None for c in counts):
            vals.append(None)
            continue
        v = sum(cs.nz(c) for c in counts)
        if basis == "건수":
            vals.append(v)
        elif basis == "점유율":
            vals.append((v / mkt[k] * 100) if mkt[k] else None)
        else:
            own = sum(cs.nz(cs.listings_at(D, cp, i, sd)) for cp in mine_cps)
            vals.append((v / own * 100) if own else None)

    if not any(cs.nz(v) for v in vals):
        st.info(f"{_eun(selected)} {focus} 관련 지역 자료가 없습니다.")
        return

    lab = _own(selected)
    st.plotly_chart(_sido_choropleth(sidos, vals, digits=fmt["digits"], suffix=fmt["suffix"]),
                    use_container_width=True, config={"displayModeBar": False})
    st.markdown(
        f'<div class="ov-footnote">색이 진할수록 {lab}의 {focus} {basis}이 높은 시·도다. '
        '시/군/구 단위 경계 데이터가 없어 시/도 단위로 본다.</div>', unsafe_allow_html=True)



def _share_table(D, selected, T, include_hg, methods, live0, tot_l0):
    """CP 하나의 방식별 점유율 표(전국 고정) — 개별 방식 + '집주인 방식' 소계를
    구성비 내림차순으로. 지역을 바꿔가며 보는 건 같은 탭 아래쪽 드릴다운 표
    (_section_methods)의 몫이라, 여기는 항상 전국 값만 다룬다."""
    sel_i = T["i"]
    mine_l = cs.method_vec(D, selected, sel_i, cs.NATION)

    if all(v is None for v in mine_l):
        st.info(f"{_eun(selected)} 이 자료에 검증방식 구분이 없습니다 "
                "(지역·매물유형만 존재). 다른 CP를 선택하면 볼 수 있습니다.")
        return

    mine_sum = sum(cs.nz(v) for v in mine_l)
    lab = _own(selected)

    # 이 시점에 실제로 값이 잡히는 방식만 (사전매물은 전 기간 0, 전화확인은 2026-03부터 0)
    live = [j for j in range(len(methods)) if tot_l0[j] > 0 or cs.nz(mine_l[j]) > 0]

    order = sorted(live, key=lambda j: -cs.nz(mine_l[j]))
    own = [j for j in order if methods[j] in METHOD_SETS["집주인 방식"]]
    color = series_color(selected, selected)

    # 개별 방식 행 + 집주인 방식 소계를 한 목록으로 만들어 구성비 하나로 같이
    # 정렬한다 — 소계가 어느 개별 방식보다 커도(보통 그렇다) 위로 올라오게.
    # 소계도 다른 행과 똑같은 모양으로 두고(강조색 없음), 이름으로만 구분한다.
    rows_data = [dict(name=methods[j], mine=mine_l[j], tot=tot_l0[j],
                      mix=(cs.nz(mine_l[j]) / mine_sum * 100) if mine_sum else None,
                      sh=(cs.nz(mine_l[j]) / tot_l0[j] * 100) if tot_l0[j] else None)
                 for j in order]
    if own:
        om = sum(cs.nz(mine_l[j]) for j in own)
        ot = sum(tot_l0[j] for j in own)
        rows_data.append(dict(
            name="집주인 방식", mine=om, tot=ot,
            mix=(om / mine_sum * 100) if mine_sum else None,
            sh=(om / ot * 100) if ot else None))
    rows_data.sort(key=lambda r: -(r["mix"] or 0))

    # 구성비·점유율을 별도 열로 안 두고, 건수 칸 안에 데이터 막대 배경 + 비율을 같이 넣는다
    # (숫자와 비율이 늘 붙어 있어야 하는 값이라 열을 나누면 오히려 눈이 왔다갔다 해야 했다).
    body = ""
    for r in rows_data:
        mine_cell = f'{_num(r["mine"])}<span class="ov-dbpct">· {_pct(r["mix"], 1)}</span>'
        tot_cell = f'{_num(r["tot"])}<span class="ov-dbpct">· {_pct(r["sh"])}</span>'
        body += (f'<tr><td class="region name">{r["name"]}</td>'
                 + _databar(mine_cell, r["mix"], color)
                 + _databar(tot_cell, r["sh"], color)
                 + '</tr>')
    st.markdown(
        '<div class="ov-table-scroll"><table class="ov-table"><thead><tr>'
        f'<th class="region name">방식</th><th>{lab} 매물 수(구성비)</th>'
        f'<th>시장 매물(점유율)</th>'
        f"</tr></thead><tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
    if own:
        st.markdown(
            '<div class="ov-footnote">집주인 방식 = '
            + " + ".join(methods[j] for j in own) + '.</div>', unsafe_allow_html=True)

    notes = []
    if D["months"][sel_i] in D["meta"]["restored_months"]:
        notes.append("이 시점은 총계 행의 검증방식 값이 비어 있어 매물수를 상세 행 합으로 복원했다. "
                     "회원수는 중복 계상 때문에 복원이 불가능해 – 로 둔다.")
    if notes:
        st.markdown('<div class="ov-footnote">' + "<br>".join(notes) + "</div>",
                    unsafe_allow_html=True)


def _section_methods(D, selected, T, include_hg, region=cs.NATION, dl_slot=None):
    """시도 > 시군구 계층 표 — 지역을 바꿔가며 검증방식별 매물수/구성비/점유율을 본다.
    같은 탭 위쪽의 'CP별 매물 검증방식 구성'(_share_table)은 전국 고정 요약이고,
    여기는 '지역'이 주어인 드릴다운만 맡는다 — 요약과 드릴다운이 같은 숫자를 반복하지 않도록.
    제목과 지역 선택 컨트롤은 호출하는 쪽(_tab_method)이 그린다."""
    sel_i = T["i"]
    methods = D["methods"]
    tot_l0 = cs.method_market(D, sel_i, include_hg, region)
    live0 = [j for j in range(len(methods)) if tot_l0[j] > 0]
    if not live0:
        st.info("이 지역에 검증방식 데이터가 없습니다.")
        return

    # 검증방식 자료가 없는 CP(한공협)를 섞으면 매물수 합과 방식 합이 어긋나므로 뺀다.
    if selected == ALL:
        cps = [c for c in cs.market_cps(D, include_hg)
               if c not in D["meta"]["no_method"]]
    elif selected == cs.PROPTIER:
        cps = list(cs.PROPTIER_PARTS)
    else:
        cps = [selected]
    if dl_slot is not None:
        with dl_slot:
            _dl_button(
                _drill_frame(D, cps, sel_i, region, methods, live0, tot_l0),
                f"검증방식_지역_{_cp_label(selected)}_{region}_{D['months'][sel_i]}",
                "cp_m_dl", "검증방식지역")
    st.markdown(_drill_table(D, cps, sel_i, region, methods, live0, tot_l0),
                unsafe_allow_html=True)
    st.markdown('<div class="ov-footnote">시·도 행을 누르면 그 아래 시·군·구가 펼쳐진다. '
                '구성비는 그 지역 매물 중 해당 방식의 비율, 점유율은 그 방식 시장에서의 몫이다.'
                '</div>', unsafe_allow_html=True)


# ── 섹션 8 ───────────────────────────────────────────────────────────────────


def _region_all(D, selected, T, include_hg):
    """CP x 시도 점유율 히트맵. 어느 CP가 어디에 강한지 색으로 찾는다.
    개별 CP를 보고 있으면 그 행을 맨 위로 올리고 굵게 강조한다."""
    i = T["i"]
    sidos = D["sidos"]
    tot = cs.market_vec(D, "sl", i, include_hg, len(sidos))
    cps = _ranked_cps(D, i, include_hg, "l")

    z, rows = [], []
    for c in cps:
        mine = D["d"][c]["sl"][i] or [0] * len(sidos)
        vals = [(cs.nz(mine[j]) / tot[j] * 100) if tot[j] else None for j in range(len(sidos))]
        if not any(v for v in vals):
            continue
        rows.append(c)
        z.append(vals)

    st.markdown('<div class="ov-panel-title">CP별 시·도 지역 점유율 현황</div>',
                unsafe_allow_html=True)
    hl = None if selected == ALL else (
        set(cs.PROPTIER_PARTS) if selected == cs.PROPTIER else {selected})
    st.plotly_chart(_heatmap(rows, sidos, z, highlight=hl), use_container_width=True,
                    config={"displayModeBar": False})


# ── 섹션 9 ───────────────────────────────────────────────────────────────────
def _section_notes(D):
    mm = D["meta"]
    dates = " · ".join(f"{lab} {d}" for lab, d in zip(D["labels"], D["dates"]))
    st.markdown(
        f"""<div class="cp-note"><ul>
<li><b>회원수는 더하면 안 됩니다.</b> 한 회원이 여러 지역·매물유형·검증방식에 걸쳐 중복으로 세어져,
상세 행을 다 더하면 실제의 {mm['cover_min']}~{mm['cover_max']}배가 됩니다. 그래서 이 화면의 회원 점유율은
전부 총계 행에서만 계산합니다. 지역별·검증방식별 회원수는 같은 축 안에서 CP끼리 비교할 때만 쓰세요.</li>

<li><b>회원수 = 고유 중개사무소 수가 아니라 CP 계약 건수입니다.</b> 회원은 CP별로 각각 책정돼서,
같은 중개사가 2개 CP를 쓰면 양쪽에 1명씩 잡힙니다. 전 CP 회원수를 더한 값은 시장의 중개사무소 수보다 큽니다.</li>

<li><b>수집일이 월말이 아니고 제각각입니다.</b> {dates}. 연월구분에 2026-08이 없어
2026-09 수집분을 <b>8월</b>로 표기했습니다. 전월 대비 증감은 '달'이 아니라 '수집 시점' 간격이라
구간 길이가 일정하지 않습니다.</li>

<li><b>{"·".join(mm['restored_months'])} 시점은 총계 행의 검증방식 칸이 비어 있습니다.</b>
매물수는 상세 행 합으로 복원했고(다른 시점으로 검산하면 오차 0), 회원수는 중복 계상 때문에
복원이 불가능해 – 로 둡니다.</li>

<li><b>{"·".join(mm['no_method'])}은 전 기간 검증방식 자료가 없습니다.</b> 지역·매물유형만 있어
검증방식 섹션에는 나오지 않습니다.</li>

<li><b>실질 검증방식은 7종입니다.</b> {"·".join(mm['dead_methods'])}은 전 기간 모든 CP가 0건이고,
전화확인은 {mm['phone_last']} 이후로 0건입니다.</li>

<li><b>{"·".join(mm['gone'])}는 시장에서 빠졌습니다.</b> 이후 시점엔 행 자체가 없어서,
결측이 아니라 0으로 처리했습니다.</li>

<li><b>총계와 상세의 구분은 매물그룹이 '전체'인지로만 판별합니다.</b> 시도로 거르면
시도가 비어 있는 총계 행 하나가 상세에 섞여 그 CP의 매물수가 2배로 부풀어 오릅니다.</li>
</ul></div>""", unsafe_allow_html=True)

    checks = "".join(f"<li>✅ {line}</li>" for line in mm.get("validation", []))
    st.markdown(
        '<div class="cp-note" style="margin-top:6px;">'
        '<b>집계 검증 결과 (assert)</b><ul>' + checks + "</ul>"
        f"<div class=\"ov-footnote\">원자료 {mm['rows']:,}행 = 총계 {mm['tot_rows']}행 + "
        f"상세 {mm['det_rows']:,}행 · 출처 {mm['source']}</div></div>",
        unsafe_allow_html=True)


# ── KPI ──────────────────────────────────────────────────────────────────────
# ── 탭 본문 ──────────────────────────────────────────────────────────────────
def _tab_share(D, selected, T, include_hg):
    """탭1 시장 점유율 — 전체 모드 전용(개별 CP는 탭 자체가 없다, render() 참고).
    비교 관점의 히트맵과 집계표를 보여준다."""
    _region_all(D, selected, T, include_hg)
    _rule()
    _section_rank(D, selected, T, include_hg)


def _attr_matrix(D, T, include_hg, axis_key, axis_names):
    """CP x (권역 또는 매물유형) 행렬과 축별 시장 합계를 만든다. 매물수 기준."""
    i = T["i"]
    cps, mat = [], []
    for c in _ranked_cps(D, i, include_hg, "l"):
        row = [cs.nz(v) for v in (D["d"][c][axis_key][i] or [0] * len(axis_names))]
        if sum(row) == 0:
            continue
        cps.append(c)
        mat.append(row)
    tot = cs.market_vec(D, axis_key, i, include_hg, len(axis_names))
    return cps, mat, tot


def _attr_frame(cps, mat, tot, axis_names):
    """속성 구성 표의 원본 데이터. 화면 표와 엑셀이 같은 숫자를 쓰도록 한 곳에서 만든다
    (엑셀에는 서식 없는 raw 숫자를 넣어 받는 쪽에서 다시 계산할 수 있게 한다)."""
    recs = []
    for k, c in enumerate(cps + ["시장 전체"]):
        row = mat[k] if k < len(cps) else tot
        base = sum(row) or 1
        r = {"CP": c, "매물수": sum(row)}
        for j, n in enumerate(axis_names):
            r[f"{n} 건수"] = row[j]
            r[f"{n} 구성비(%)"] = round(row[j] / base * 100, 1)
            r[f"{n} 점유율(%)"] = (100.0 if k >= len(cps)
                                 else (round(row[j] / tot[j] * 100, 2) if tot[j] else None))
        recs.append(r)
    return pd.DataFrame(recs)


def _section_zone_bias(D, selected, T, include_hg):
    """CP별 권역별(수도권/지방) 구성비 — 매물수 기준 지역 편중, 시·도 > 시·군·구까지 드릴다운.
    검증방식과 무관하게 '어디에 매물이 몰려 있나'만 본다."""
    i = T["i"]
    stamp = D["months"][i]
    # 차트 보기엔 엑셀 버튼이 없어 그 칸(c3)만큼 오른쪽이 비어 보였다 — 표로 보기일 때만
    # 칸을 셋으로 나누고, 차트 보기는 둘로 합쳐 토글이 진짜 오른쪽 끝까지 붙게 한다.
    wide = (st.session_state.get("cp_zone_view") or "차트 보기") != "표로 보기"
    cols = st.columns([1.72, 1.48] if wide else [1.72, 1.0, 0.48])
    c1, c2 = cols[0], cols[1]
    c3 = cols[2] if len(cols) > 2 else None
    with c1:
        st.markdown('<div class="ov-panel-title" style="padding-top:9px;">'
                    'CP별 권역별(수도권/지방) 구성비</div>',
                    unsafe_allow_html=True)
    with c2:
        view = st.segmented_control(
            "보기", ["차트 보기", "표로 보기"], default="차트 보기",
            key="cp_zone_view", label_visibility="collapsed") or "차트 보기"

    cps, mat, tot = _attr_matrix(D, T, include_hg, "zl", D["zones"])
    if not cps:
        st.info("이 시점에 표시할 CP가 없습니다.")
        return

    me = set(cs.PROPTIER_PARTS) if selected == cs.PROPTIER else {selected}

    if view == "차트 보기":
        # 특정 CP를 고르면 그 막대만 선명하게, 나머지는 흐리게. 'CP사 전체'면 전부 선명하게.
        # 예전엔 권역을 눌러 시·도 세부를 여기서 또 열었는데, 아래 '지역별 검증 방식'
        # 표가 지역 선택(수도권/지방 포함)에 매물수까지 이미 보여줘서 그 세부가 통째로
        # 중복이었다 — 클릭 드릴다운은 없애고 차트만 남긴다.
        st.plotly_chart(
            _stacked100(cps, D["zones"], mat,
                        highlight=None if selected == ALL else me),
            use_container_width=True, config={"displayModeBar": False})
        return

    # 권역(수도권/지방)만으로는 거칠어서, 시·도 > 시·군·구까지 내려가 본다.
    mine_cps = (cs.market_cps(D, include_hg) if selected == ALL
                else (list(cs.PROPTIER_PARTS) if selected == cs.PROPTIER
                      else [selected]))
    lab = _own(selected)
    frame = _region_drill_frame(D, mine_cps, cs.market_cps(D, include_hg), i, lab)
    with c3:
        _dl_button(frame, f"CP별_권역편중_{_cp_label(selected)}_{stamp}",
                   "cp_t2_dl", "권역편중")
    st.markdown(_region_drill_html(D, frame, lab), unsafe_allow_html=True)
    st.markdown(
        f'<div class="ov-footnote">시·도 행을 누르면 그 아래 시·군·구가 펼쳐진다. '
        f'{lab} 내 구성비는 {lab}의 전국 매물 중 그 지역이 차지하는 비율, '
        '점유율은 그 지역 시장에서의 몫이다.</div>', unsafe_allow_html=True)


def _section_listing_mix(D, selected, T, include_hg):
    """매물 유형 구성 — 매물 종류(아파트·오피스텔 등) 구성비. 지역 축과 무관한 '무엇' 질문."""
    i = T["i"]
    stamp = D["months"][i]
    # 차트 보기엔 엑셀 버튼이 없어 그 칸(c3)만큼 오른쪽이 비어 보였다 — 표로 보기일 때만
    # 칸을 셋으로 나누고, 차트 보기는 둘로 합쳐 토글이 진짜 오른쪽 끝까지 붙게 한다.
    wide = (st.session_state.get("cp_mix_view") or "차트 보기") != "표로 보기"
    cols = st.columns([1.72, 1.48] if wide else [1.72, 1.0, 0.48])
    c1, c2 = cols[0], cols[1]
    c3 = cols[2] if len(cols) > 2 else None
    with c1:
        st.markdown('<div class="ov-panel-title" style="padding-top:9px;">'
                    'CP별 매물 유형 구성 (공동/비공동/비공동비주택)</div>',
                    unsafe_allow_html=True)
    with c2:
        view = st.segmented_control(
            "보기", ["차트 보기", "표로 보기"], default="차트 보기",
            key="cp_mix_view", label_visibility="collapsed") or "차트 보기"

    cps, mat, tot = _attr_matrix(D, T, include_hg, "gl", D["groups"])
    if not cps:
        st.info("이 시점에 표시할 CP가 없습니다.")
        return

    me = set(cs.PROPTIER_PARTS) if selected == cs.PROPTIER else {selected}

    if view == "차트 보기":
        st.plotly_chart(
            _stacked100(cps, D["groups"], mat,
                        highlight=None if selected == ALL else me),
            use_container_width=True, config={"displayModeBar": False})
        return

    axis_names = D["groups"]
    frame = _attr_frame(cps, mat, tot, axis_names)
    with c3:
        _dl_button(frame, f"CP별_매물유형_{stamp}", "cp_mix_dl", "매물유형")

    head = "".join(f'<th colspan="3">{n}</th>' for n in axis_names)
    sub = "".join('<th class="dim">건수</th><th>구성비</th><th>점유율</th>'
                  for _ in axis_names)
    body = ""
    for k, c in enumerate(cps):
        base = sum(mat[k]) or 1
        tds = "".join(
            f'<td class="dim">{_num(mat[k][j])}</td>'
            f'<td>{_pct(mat[k][j] / base * 100, 1)}</td>'
            f'<td>{_pct((mat[k][j] / tot[j] * 100) if tot[j] else None, 2)}</td>'
            for j in range(len(axis_names)))
        cls = ' class="me"' if c in me else ""
        body += (f'<tr{cls}><td class="region name">{c}</td>'
                 f'<td>{_num(base)}</td>{tds}</tr>')
    mkt_base = sum(tot) or 1
    tds = "".join(f'<td class="dim">{_num(tot[j])}</td>'
                  f'<td>{_pct(tot[j] / mkt_base * 100, 1)}</td><td>100.00%</td>'
                  for j in range(len(axis_names)))
    body += (f'<tr class="me"><td class="region name">시장 전체</td>'
             f'<td>{_num(mkt_base)}</td>{tds}</tr>')
    st.markdown(
        '<div class="ov-table-scroll"><table class="ov-table"><thead>'
        '<tr><th class="region name" rowspan="2">CP</th><th rowspan="2">매물수</th>'
        f'{head}</tr><tr>{sub}</tr></thead><tbody>{body}</tbody></table></div>',
        unsafe_allow_html=True)
    st.markdown(
        '<div class="ov-footnote">구성비 = 그 CP 매물이 각 칸에 나뉜 비율(차트와 같은 값) · '
        '점유율 = 그 칸의 시장에서 그 CP가 차지하는 몫. 매물수는 가산 가능해서 쪼갠 합이 '
        '총계와 정확히 맞는다.</div>', unsafe_allow_html=True)


def _tab_method(D, selected, T, include_hg):
    """탭2 검증 방식 — 검증방식과 관련된 화면만 모은다: 지역 히트맵/지도와 CP별 검증방식
    구성을 좌우로 나란히, 그 아래 지역별 검증방식 표. 매물유형·권역(수도권/지방) 구성비는
    구성 비교 탭으로 옮겼다."""
    focus = _hm_metric()
    col_map, col_share = st.columns([1.25, 1.0])
    with col_map:
        _region_methods_all(D, selected, T, include_hg, focus)
    with col_share:
        sel_i = T["i"]
        methods = D["methods"]
        tot_l0 = cs.method_market(D, sel_i, include_hg, cs.NATION)
        live0 = [j for j in range(len(methods)) if tot_l0[j] > 0]
        st.markdown('<div class="ov-panel-title" style="padding-top:9px;">CP별 매물 검증방식 구성</div>',
                    unsafe_allow_html=True)
        # 왼쪽(지도) 칸은 제목 밑에 드롭다운 줄 + 지표토글·엑셀 줄이 하나 더 있어 지도가
        # 그만큼 아래에서 시작한다. 전체 모드는 바로 아래에 만드는 범위 토글이 그 자리를
        # 채우지만, 개별 모드(표)·데이터 없음은 대신할 줄이 없어 어긋나 보여 빈 칸을 넣는다.
        if not live0:
            st.markdown('<div style="height:75px;"></div>', unsafe_allow_html=True)
            st.info("이 시점에 검증방식 데이터가 없습니다.")
        elif selected == ALL:
            _methods_all_chart(D, T, include_hg, cs.NATION, methods, live0)
        else:
            st.markdown('<div style="height:75px;"></div>', unsafe_allow_html=True)
            _share_table(D, selected, T, include_hg, methods, live0, tot_l0)
    _rule()

    # 지역 필터 — 고르면 표가 전부 그 지역 기준으로 다시 계산된다.
    # 제목이 선택한 지역을 달고 있어야 해서, 위젯을 만들기 전에 값을 먼저 읽는다.
    opts = cs.region_options(D)
    region = st.session_state.get("cp_region")
    region = region if region in opts else cs.NATION
    # 지역 선택 드롭다운은 옵션이 짧은 이름(전국/수도권/서울 등)뿐이라 넓을 필요가 없다 —
    # 제목 칸을 필요한 만큼만 남기고 좁혀서, 드롭다운이 엑셀 버튼 바로 옆으로 붙게 한다.
    c1, c2, c3 = st.columns([1.4, 0.6, 0.6])
    with c1:
        st.markdown(f'<div class="ov-panel-title" style="padding-top:9px;">'
                    f'지역별 검증 방식 · {region}</div>', unsafe_allow_html=True)
    with c2:
        st.selectbox("지역", opts, key="cp_region", label_visibility="collapsed")

    _section_methods(D, selected, T, include_hg, region, dl_slot=c3)


def _tab_compose(D, selected, T, include_hg):
    """탭3 구성 비교 — 검증방식과 무관한 속성 구성비만 모은다: 매물 유형, 권역(수도권/지방)."""
    _section_listing_mix(D, selected, T, include_hg)
    _rule()
    _section_zone_bias(D, selected, T, include_hg)


def _tab_etc(D, selected, T, include_hg):
    """탭4 특이사항 — CP사별 이슈 현황과 생산성 랭킹, 그리고 데이터 주의사항.
    전 CP를 훑는 내용이라 개별 CP를 볼 땐 이 탭 자체를 숨긴다(render() 참고)."""
    _section_issues(D, selected, T, include_hg)
    _rule()
    _per_member_rank(D, selected, T, include_hg)
    _rule()
    with st.expander("데이터 주의사항 · 집계 검증"):
        _section_notes(D)


def _kpi_all(D, T, include_hg):
    """전체 모드 KPI — 자사가 없으니 점유율 대신 시장 규모와 집중도를 본다."""
    i, ci = T["i"], T["cmp"]
    cps = cs.market_cps(D, include_hg)
    tm, tl = cs.market(D, "m", i, include_hg), cs.market(D, "l", i, include_hg)
    pm = cs.market(D, "m", ci, include_hg) if ci is not None else None
    pl = cs.market(D, "l", ci, include_hg) if ci is not None else None
    prev_lab = D["labels"][ci] if ci is not None else None

    active = sum(1 for c in cps if cs.nz(D["d"][c]["m"][i]) > 0)
    p_active = (sum(1 for c in cps if cs.nz(D["d"][c]["m"][ci]) > 0)
                if ci is not None else None)
    shares = sorted((cs.nz(D["d"][c]["m"][i]) / tm * 100) for c in cps)[::-1] if tm else []
    top3 = sum(shares[:3]) if shares else None
    hhi = sum(s * s for s in shares) if shares else None
    per = (tl / tm) if tm else None
    pper = (pl / pm) if pm else None

    def delta(cur, prev, dec=1):
        g = _growth(cur, prev)
        return ('<div class="delta">–</div>' if g is None
                else f'<div class="delta">{prev_lab} 대비 {_signed(g, dec)}</div>')

    st.markdown(
        '<div class="ov-stats">'
        f'<div class="ov-stat"><div class="label">시장 전체 회원 (CP 계약 건수)</div>'
        f'<div class="value">{_num(tm)}</div>{delta(tm, pm)}'
        f'<div class="sub">한공협 {"포함" if include_hg else "제외"}</div></div>'

        f'<div class="ov-stat"><div class="label">시장 전체 매물수</div>'
        f'<div class="value">{_num(tl)}</div>{delta(tl, pl)}</div>'

        f'<div class="ov-stat"><div class="label">활동 CP 수</div>'
        f'<div class="value">{active}</div>'
        + (f'<div class="delta">{prev_lab} 대비 {active - p_active:+d}개사</div>'
           if p_active is not None else '<div class="delta">–</div>')
        + f'<div class="sub">전체 {len(cps)}개사 중 회원 1건 이상</div></div>'

        f'<div class="ov-stat"><div class="label">상위 3사 점유율</div>'
        f'<div class="value">{_pct(top3, 1)}</div>'
        f'<div class="delta">회원 기준 집중도</div>'
        f'<div class="sub">HHI {_num(hhi)}</div></div>'

        f'<div class="ov-stat"><div class="label">평균 회원당 매물</div>'
        f'<div class="value">{_num(per, 1)}</div>{delta(per, pper)}</div>'
        "</div>", unsafe_allow_html=True)


def _kpi(D, selected, T, include_hg):
    if selected == ALL:
        return _kpi_all(D, T, include_hg)
    d = D["d"][selected]
    sel_i, prev_i = T["i"], T["cmp"]
    prev_lab = D["labels"][prev_i] if prev_i is not None else None

    m, l = d["m"][sel_i], d["l"][sel_i]
    pm = d["m"][prev_i] if prev_i is not None else None
    pl = d["l"][prev_i] if prev_i is not None else None

    sh_ex = cs.share_series(D, selected, "m", False)
    sh_in = cs.share_series(D, selected, "m", True)
    ls_ex = cs.share_series(D, selected, "l", False)
    ls_in = cs.share_series(D, selected, "l", True)
    mem_sh = (sh_in if include_hg else sh_ex)
    lst_sh = (ls_in if include_hg else ls_ex)

    per = (l / m) if (m and l is not None) else None
    pper = (pl / pm) if (pm and pl is not None) else None

    # 한공협 자신을 보고 있을 땐 '한공협 제외' 분모가 자기를 뺀 값이라 뜻이 없다 — 병기하지 않는다.
    def both(ex, inc):
        if selected == cs.HANGONG:
            return '<div class="sub">한공협 포함 기준 (자기 자신은 분모에서 뺄 수 없음)</div>'
        return (f'<div class="sub">한공협 제외 {_pct(ex[sel_i])}<br>'
                f'포함 {_pct(inc[sel_i])}</div>')

    def delta(cur, prev, dec=1):
        g = _growth(cur, prev)
        if g is None:
            return '<div class="delta">–</div>'
        return f'<div class="delta">{prev_lab} 대비 {_signed(g, dec)}</div>'

    def dshare(s):
        if prev_i is None or s[sel_i] is None or s[prev_i] is None:
            return '<div class="delta">–</div>'
        return f'<div class="delta">{prev_lab} 대비 {_signed(s[sel_i] - s[prev_i], 2, "%p")}</div>'

    st.markdown(
        '<div class="ov-stats">'
        f'<div class="ov-stat"><div class="label">회원수 (CP 계약 건수)</div>'
        f'<div class="value">{_num(m)}</div>{delta(m, pm)}</div>'

        f'<div class="ov-stat"><div class="label">회원 점유율</div>'
        f'<div class="value">{_pct(mem_sh[sel_i])}</div>{dshare(mem_sh)}'
        f"{both(sh_ex, sh_in)}</div>"

        f'<div class="ov-stat"><div class="label">매물수</div>'
        f'<div class="value">{_num(l)}</div>{delta(l, pl)}</div>'

        f'<div class="ov-stat"><div class="label">매물 점유율</div>'
        f'<div class="value">{_pct(lst_sh[sel_i])}</div>{dshare(lst_sh)}'
        f"{both(ls_ex, ls_in)}</div>"

        f'<div class="ov-stat"><div class="label">회원당 매물</div>'
        f'<div class="value">{_num(per, 1)}</div>{delta(per, pper)}</div>'
        "</div>", unsafe_allow_html=True)


# ── 진입점 ───────────────────────────────────────────────────────────────────
def render():
    version = cs.data_version()
    if version is None:
        st.title(auth.PAGE_CP_STATUS)
        st.info(
            "아직 CP 원본이 올라와 있지 않습니다. 관리자 계정으로 "
            f"**{auth.PAGE_ADMIN} → CP 원본 업로드**에서 `{cs.XLSX_NAME}`을 올려주세요.")
        return

    D = cs.load(version)

    with st.container(key="cp_root"):
        st.markdown(_EXTRA_CSS, unsafe_allow_html=True)
        st.markdown(
            f'<div class="ov-topline"><h1 style="margin:0;">{auth.PAGE_CP_STATUS}</h1></div>',
            unsafe_allow_html=True)

        # ---- 전역 컨트롤 ----
        options = _cp_options(D)
        default_i = options.index(ALL) if ALL in options else 0
        # 기간 슬라이더는 넓어야 하고 시점 드롭다운은 그럴 필요가 없다. 어느 쪽인지는
        # 위젯을 만들기 전에 session_state에서 읽어 칸 너비를 정한다.
        wide = (st.session_state.get("cp_tmode") or "시점") == "기간"
        c1, c0, c2, c3 = st.columns([1.05, 0.8, 2.5 if wide else 1.2, 1.05])
        selected = c1.selectbox("CP", options, index=default_i, key="cp_sel",
                                format_func=_cp_label)
        mode = c0.segmented_control("보기", ["시점", "기간"], default="시점",
                                    key="cp_tmode") or "시점"
        with c2:
            if mode == "기간":
                rng = st.select_slider(
                    "기간", options=D["labels"],
                    value=(D["labels"][0], D["labels"][-1]), key="cp_range")
                month_lab = None
            else:
                rng = None
                month_lab = st.selectbox(
                    "시점", D["labels"], index=len(D["labels"]) - 1,
                    key="cp_month") or D["labels"][-1]
        T = _period(D, mode, month_lab, rng)

        # 한공협을 보고 있을 땐 분모에서 자기 자신을 뺄 수 없으므로 자동 포함하되,
        # 사용자가 켜둔 값(cp_hg_user)은 건드리지 않고 그대로 보존한다.
        is_hg = selected == cs.HANGONG
        with c3:
            if is_hg:
                st.toggle("한공협 포함", value=True, disabled=True, key="cp_hg_forced")
                st.caption("한공협 선택 시 자동 포함")
                include_hg = True
            else:
                include_hg = st.toggle("한공협 포함", key="cp_hg_user")
                st.caption("분모(시장 전체)에 협회를 넣을지")

        _kpi(D, selected, T, include_hg)

        if selected != ALL:
            # 개별 CP는 KPI 카드에 이미 내 수치가 다 있어 '시장 점유율' 탭을 통째로
            # 둘 자리가 없다 — 유일하게 남아 있던 내용(다른 CP와 비교)만 탭 밖,
            # KPI 바로 아래에 접어서 둔다.
            with st.expander("다른 CP와 비교해서 보기"):
                _section_rank(D, selected, T, include_hg)

        # 다른 메뉴(중개업 시장 동향·공인중개사 현황)와 같은 탭 UI.
        # st.tabs는 숨은 탭 내용까지 전부 렌더하지만 서버측 40ms 수준이라 체감 차이가 없다.
        # 시장 점유율·특이사항은 전체 모드 전용이라 개별 CP를 볼 땐 둘 다 뺀다.
        names = (SECTIONS + [SECTION_ETC]) if selected == ALL else SECTIONS[1:]
        tabs = st.tabs(names)

        if selected == ALL:
            with tabs[0]:
                _tab_share(D, selected, T, include_hg)
            with tabs[1]:
                _tab_method(D, selected, T, include_hg)
            with tabs[2]:
                _tab_compose(D, selected, T, include_hg)
            with tabs[3]:
                _tab_etc(D, selected, T, include_hg)
        else:
            with tabs[0]:
                _tab_method(D, selected, T, include_hg)
            with tabs[1]:
                _tab_compose(D, selected, T, include_hg)
