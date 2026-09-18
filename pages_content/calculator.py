# -*- coding: utf-8 -*-
"""공헌이익 시뮬레이터: '이실장 제휴 룸 계산기'를 이 앱 스타일 그대로 네이티브 위젯으로 재구현."""
import streamlit as st

import auth

PG_RATE = 0.02508  # PG수수료(부가세 별도 2.28%) x VAT 1.1

# (지역, 상품, 상품가, 관리수수료율_표기준, 유치수수료_표기준, 쿠폰비용, 할인율)
DATA = [
    {"region": "수도권·충청", "rows": [
        {"term": "6개월", "product": "Lite", "P": 120000, "a": 0.32, "acq": 10000, "coupon": 26350, "disc": 0.00},
        {"term": "6개월", "product": "Basic", "P": 240000, "a": 0.22, "acq": 25000, "coupon": 52700, "disc": 0.00},
        {"term": "6개월", "product": "Mega", "P": 600000, "a": 0.14, "acq": 100000, "coupon": 52700, "disc": 0.00},
        {"term": "1년", "product": "Lite", "P": 216000, "a": 0.32, "acq": 10000, "coupon": 52700, "disc": 0.10},
        {"term": "1년", "product": "Basic", "P": 432000, "a": 0.22, "acq": 25000, "coupon": 105400, "disc": 0.10},
        {"term": "1년", "product": "Mega", "P": 1080000, "a": 0.14, "acq": 100000, "coupon": 105400, "disc": 0.10},
    ]},
    {"region": "부산·울산·경남", "rows": [
        {"term": "6개월", "product": "Lite", "P": 96000, "a": 0.42, "acq": 10000, "coupon": 26350, "disc": 0.20},
        {"term": "6개월", "product": "Basic", "P": 192000, "a": 0.32, "acq": 25000, "coupon": 52700, "disc": 0.20},
        {"term": "6개월", "product": "Mega", "P": 480000, "a": 0.24, "acq": 100000, "coupon": 52700, "disc": 0.20},
        {"term": "1년", "product": "Lite", "P": 168000, "a": 0.42, "acq": 10000, "coupon": 52700, "disc": 0.30},
        {"term": "1년", "product": "Basic", "P": 336000, "a": 0.32, "acq": 25000, "coupon": 105400, "disc": 0.30},
        {"term": "1년", "product": "Mega", "P": 840000, "a": 0.24, "acq": 100000, "coupon": 105400, "disc": 0.30},
    ]},
    {"region": "대구·경북", "rows": [
        {"term": "6개월", "product": "Lite", "P": 90000, "a": 0.42, "acq": 10000, "coupon": 26350, "disc": 0.25},
        {"term": "6개월", "product": "Basic", "P": 144000, "a": 0.32, "acq": 25000, "coupon": 52700, "disc": 0.40},
        {"term": "6개월", "product": "Mega", "P": 360000, "a": 0.24, "acq": 100000, "coupon": 52700, "disc": 0.40},
        {"term": "1년", "product": "Lite", "P": 180000, "a": 0.42, "acq": 10000, "coupon": 52700, "disc": 0.25},
        {"term": "1년", "product": "Basic", "P": 288000, "a": 0.32, "acq": 25000, "coupon": 105400, "disc": 0.40},
        {"term": "1년", "product": "Mega", "P": 720000, "a": 0.24, "acq": 100000, "coupon": 105400, "disc": 0.40},
    ]},
    {"region": "호남·강원·제주", "rows": [
        {"term": "6개월", "product": "Lite", "P": 90000, "a": 0.42, "acq": 10000, "coupon": 26350, "disc": 0.25},
        {"term": "6개월", "product": "Basic", "P": 168000, "a": 0.32, "acq": 25000, "coupon": 52700, "disc": 0.30},
        {"term": "6개월", "product": "Mega", "P": 420000, "a": 0.24, "acq": 100000, "coupon": 52700, "disc": 0.30},
        {"term": "1년", "product": "Lite", "P": 180000, "a": 0.42, "acq": 10000, "coupon": 52700, "disc": 0.25},
        {"term": "1년", "product": "Basic", "P": 336000, "a": 0.32, "acq": 25000, "coupon": 105400, "disc": 0.30},
        {"term": "1년", "product": "Mega", "P": 840000, "a": 0.24, "acq": 100000, "coupon": 105400, "disc": 0.30},
    ]},
]

MGMT_BASE_RATE = {
    "Lite": {"metro": 0.32, "local": 0.42},
    "Basic": {"metro": 0.22, "local": 0.32},
    "Mega": {"metro": 0.14, "local": 0.24},
}

DEFAULT_COUPON = {
    "Lite": {"general": {"qty": 5, "price": 1670}, "owner": {"qty": 15, "price": 1200}},
    "그 외": {"general": {"qty": 10, "price": 1670}, "owner": {"qty": 30, "price": 1200}},
}

# session_state 키 이름과 기본값 (계정별이 아니라 세션 내에서만 유지되는 계산기 상태)
_DEFAULTS = {
    "calc_disc_mode": "없음", "calc_disc_value": 0,
    "calc_acq_mode": "표기준", "calc_acq_value": 0,
    "calc_mgmt_mode": "표기준", "calc_mgmt_value": 0, "calc_mgmt_renew_mode": "낮춘 요율",
    "calc_trial_mode": "없음", "calc_trial_value": 0,
    "calc_term": "6개월", "calc_grid_term": "6개월",
    "calc_cpn_lite_general_qty": 5, "calc_cpn_lite_general_price": 1670,
    "calc_cpn_lite_owner_qty": 15, "calc_cpn_lite_owner_price": 1200,
    "calc_cpn_other_general_qty": 10, "calc_cpn_other_general_price": 1670,
    "calc_cpn_other_owner_qty": 30, "calc_cpn_other_owner_price": 1200,
}


def _ensure_state():
    for key, value in _DEFAULTS.items():
        st.session_state.setdefault(key, value)


def _reset_all():
    for key, value in _DEFAULTS.items():
        st.session_state[key] = value


def _reset_coupon():
    for key in (
        "calc_cpn_lite_general_qty", "calc_cpn_lite_general_price",
        "calc_cpn_lite_owner_qty", "calc_cpn_lite_owner_price",
        "calc_cpn_other_general_qty", "calc_cpn_other_general_price",
        "calc_cpn_other_owner_qty", "calc_cpn_other_owner_price",
    ):
        st.session_state[key] = _DEFAULTS[key]


def _current_coupon() -> dict:
    s = st.session_state
    return {
        "Lite": {
            "general": {"qty": s["calc_cpn_lite_general_qty"], "price": s["calc_cpn_lite_general_price"]},
            "owner": {"qty": s["calc_cpn_lite_owner_qty"], "price": s["calc_cpn_lite_owner_price"]},
        },
        "그 외": {
            "general": {"qty": s["calc_cpn_other_general_qty"], "price": s["calc_cpn_other_general_price"]},
            "owner": {"qty": s["calc_cpn_other_owner_qty"], "price": s["calc_cpn_other_owner_price"]},
        },
    }


def _won(n) -> str:
    return f"{round(n):,}원"


def _pct(n, digits=1) -> str:
    return f"{n * 100:.{digits}f}%"


def _round1(n) -> float:
    return round(n * 1000) / 1000  # 화면 표시(소수점 1자리 %) 기준으로 반올림해서 판정에 쓴다


def _coupon_tier(row) -> str:
    return "Lite" if row["product"] == "Lite" else "그 외"


def _coupon_base_6mo(tier, coupon_cfg) -> float:
    t = coupon_cfg[tier]
    return t["general"]["qty"] * t["general"]["price"] + t["owner"]["qty"] * t["owner"]["price"]


def _coupon_live(row, coupon_cfg) -> float:
    base = _coupon_base_6mo(_coupon_tier(row), coupon_cfg)
    return base * 2 if row["term"] == "1년" else base


def _calc_discounted(row, s):
    if s["calc_disc_mode"] == "없음":
        return row["P"]
    if s["calc_disc_mode"] == "정률":
        return row["P"] * (1 - s["calc_disc_value"] / 100)
    return max(0, row["P"] - s["calc_disc_value"])  # 정액 할인


def _calc_acq(row, s, psold):
    if s["calc_acq_mode"] == "표기준":
        return row["acq"]
    if s["calc_acq_mode"] == "정률":
        return psold * (s["calc_acq_value"] / 100)
    return s["calc_acq_value"]  # 정액


def _calc_mgmt(row, s, psold):
    if s["calc_mgmt_mode"] == "표기준":
        return row["a"] * row["P"]  # 표기준은 항상 정가 기준 고정값
    if s["calc_mgmt_mode"] == "정률":
        return psold * max(0, row["a"] - abs(s["calc_mgmt_value"]) / 100)
    return s["calc_mgmt_value"]  # 정액


def _calc_mgmt_renew(row, s):
    # 재계약에는 상품 할인이 적용되지 않으므로 항상 정가(P) 기준으로 계산한다.
    if s["calc_mgmt_mode"] == "표기준":
        return row["a"] * row["P"]
    if s["calc_mgmt_mode"] == "정률":
        rate = row["a"] if s["calc_mgmt_renew_mode"] == "기존 요율" else max(0, row["a"] - abs(s["calc_mgmt_value"]) / 100)
        return row["P"] * rate
    return s["calc_mgmt_value"]  # 정액 — 할인 여부와 무관하게 동일


def _compute_row(row, s, coupon_cfg) -> dict:
    p = row["P"]
    psold = _calc_discounted(row, s)
    acq = _calc_acq(row, s, psold)
    mgmt = _calc_mgmt(row, s, psold)
    mgmt_renew = _calc_mgmt_renew(row, s)
    pg = psold * PG_RATE
    pg_renew = p * PG_RATE
    coupon = _coupon_live(row, coupon_cfg)
    trial = abs(s["calc_trial_value"]) if s["calc_trial_mode"] == "제공" else 0

    margin_new = psold - acq - mgmt - coupon - pg - trial
    margin_renew = p - mgmt_renew - coupon - pg_renew
    rate_new = margin_new / psold if psold else 0.0
    rate_renew = margin_renew / p if p else 0.0

    floor = (p - row["acq"] - row["a"] * p - row["coupon"] - p * PG_RATE) / p
    floor_renew = floor + row["acq"] / p
    pass_new = _round1(rate_new) >= _round1(floor) - 1e-9
    pass_renew = _round1(rate_renew) >= _round1(floor_renew) - 1e-9
    passed = pass_new and pass_renew

    max_acq_won = psold - mgmt - coupon - pg - trial - floor * psold
    max_acq_pct = max_acq_won / psold if psold else 0.0

    return {
        "P": p, "Psold": psold, "acq": acq, "mgmt": mgmt, "mgmt_renew": mgmt_renew,
        "pg": pg, "pg_renew": pg_renew, "coupon": coupon, "trial": trial,
        "margin_new": margin_new, "margin_renew": margin_renew,
        "rate_new": rate_new, "rate_renew": rate_renew, "floor": floor, "floor_renew": floor_renew,
        "pass": passed, "pass_new": pass_new, "pass_renew": pass_renew,
        "max_acq_won": max_acq_won, "max_acq_pct": max_acq_pct,
        "acq_baseline": row["acq"], "mgmt_baseline": row["a"] * p, "coupon_baseline": row["coupon"],
    }


def _compare_cell(baseline, now, invert=False) -> str:
    if abs(now - baseline) < 0.5:
        return _won(now)
    increased = now > baseline
    is_bad = (not increased) if invert else increased
    cls = "up" if is_bad else "down"
    return (
        f'<div class="calc-compare"><span class="was">{_won(baseline)}</span>'
        f'<span class="arrow">→</span><span class="now {cls}">{_won(now)}</span></div>'
    )


def _compare_pct_cell(baseline, now, invert=False, digits=1) -> str:
    base_str, now_str = _pct(baseline, digits), _pct(now, digits)
    if base_str == now_str:
        return now_str
    increased = now > baseline
    is_bad = (not increased) if invert else increased
    cls = "up" if is_bad else "down"
    return (
        f'<div class="calc-compare"><span class="was">{base_str}</span>'
        f'<span class="arrow">→</span><span class="now {cls}">{now_str}</span></div>'
    )


# 상단 4개 입력 행(및 관리수수료 행)의 [세그먼트 | 값 영역] 좌우 분할 비율.
# 모든 행이 이 비율을 공유해야 값 영역의 오른쪽 끝선이 세로로 딱 맞는다.
# 관리수수료 행(입력+단위+재계약 토글까지 들어감)이 가장 넓은 값 영역을 필요로 하므로 값 영역 쪽에 더 배분한다.
_FIELD_SPLIT = (1, 2.3)

# 섹션 1(설정+참조표)과 섹션 2(공헌이익률+통과현황)의 좌/우 칼럼 분할 비율.
# 두 섹션이 같은 비율을 써야 우측 표/카드들의 좌우 끝선이 페이지 전체에서 세로로 맞는다.
_SECTION_SPLIT = (1, 1.2)


def _mode_row(label, key, options, unit_map):
    """라벨 + 한 행에 [세그먼트 라디오 | 숫자입력+단위]를 나란히 그린다.
    값 영역(vc)은 폭을 다른 행들과 통일하고, 그 안에서 내용을 오른쪽으로 붙여
    (justify-content:flex-end, CSS) 입력창의 오른쪽 끝선이 항상 같은 위치에 오게 한다.
    unit_map: {모드: 단위} (없는 모드는 입력을 숨김)"""
    st.markdown(f'<div class="calc-field-label">{label}</div>', unsafe_allow_html=True)
    value_key = key.replace("_mode", "_value")

    rc, vc = st.columns(_FIELD_SPLIT)
    with rc:
        mode = st.radio(label, options, key=key, horizontal=True, label_visibility="collapsed")
    unit = unit_map.get(mode)
    with vc:
        if unit is not None:
            with st.container(key=f"calc_value_area_{key}"):
                ic1, ic2 = st.columns([1, 1])
                with ic1:
                    st.number_input(label, key=value_key, step=1000 if unit == "원" else 1, label_visibility="collapsed")
                with ic2:
                    st.markdown(f'<div class="calc-unit">{unit}</div>', unsafe_allow_html=True)
    return mode


# 계산기 페이지 전용: 원본 HTML(세그먼트 캡슐 버튼 + 한 줄 인풋) 톤에 맞춘 CSS.
# .st-key-calc_root 로 스코프해서 다른 화면(사이드바 메뉴, 개요, 계산기 안의 "6개월/1년" 등)에는 영향 없음.
_DENSE_CSS = """
<style>
/* 계산기 화면만 콘텐츠 폭을 넓게(다른 화면의 1080px 폭에는 영향 없음) */
.stApp:has(.st-key-calc_root) .block-container { max-width: 1440px; }

.st-key-calc_root { font-size: 13px; }
.st-key-calc_root div[data-testid="stVerticalBlock"] { gap: .6rem; }
.st-key-calc_root div[data-testid="stHorizontalBlock"] { gap: 13px; align-items: center; }
/* 4등분 상단 설정 줄 / 3열 중단 카드 줄: 칼럼마다 내용 높이가 달라도 맨 위(타이틀 라인)는 항상 맞춰야 하므로
   위의 공통 center 정렬 대신 이 두 줄만 위쪽 정렬로 되돌린다 */
.st-key-calc_root [class*="st-key-calc_row_"] > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"],
.st-key-calc_root [class*="st-key-calc_hdr_row_"] > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
    align-items: flex-start !important;
}
.st-key-calc_root hr { margin: .3rem 0 !important; }
.st-key-calc_root .ov-panel-title { padding-bottom: 8px; margin-bottom: 8px; }
.st-key-calc_root .ov-panel-desc { margin-bottom: 4px; }
.st-key-calc_root .calc-field-label {
    font-size: .78rem; font-weight: 500; color: #6B756E; white-space: nowrap;
    padding-bottom: 8px; margin-bottom: 8px;
}
.st-key-calc_root .calc-col-title {
    font-size: .88rem; font-weight: 700; margin: 0; padding: 4px 0; white-space: nowrap; line-height: 1.4;
}
.st-key-calc_root .calc-unit { font-size: .8rem; color: #6B756E; padding-left: 4px; white-space: nowrap; }

/* '쿠폰 기본값으로': 흰 배경 + 옅은 테두리의 단정한 일반 버튼 */
.st-key-calc_root [class*="st-key-calc_text_btn"] div[data-testid="stButton"] button {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    color: #374151 !important;
    font-size: .78rem !important;
    font-weight: 500 !important;
    padding: 4px 12px !important;
    height: 30px !important;
    min-height: 30px !important;
    box-shadow: none !important;
}
.st-key-calc_root [class*="st-key-calc_text_btn"] div[data-testid="stButton"] button:hover {
    background: #F8F9FA !important;
    border-color: #D1D5DB !important;
    color: #111827 !important;
}

/* 6개월/1년 토글을 칼럼 우측 끝으로 정렬 (컨테이너의 flex 방향이 row/column 어느 쪽이든 오른쪽으로) */
.st-key-calc_root [class*="st-key-calc_term_right"] {
    display: flex !important;
    align-items: flex-end !important;
    justify-content: flex-end !important;
}

/* 값 영역(입력창+단위, 관리수수료는 +재계약 그룹까지): 내용을 오른쪽으로 붙여서
   각 행마다 입력창의 오른쪽 끝선이 항상 같은 위치(값 영역의 오른쪽 끝 = 좌측 패널 오른쪽 끝)에 오게 한다 */
.st-key-calc_root [class*="st-key-calc_value_area_"] div[data-testid="stHorizontalBlock"] {
    justify-content: flex-end !important;
    flex-wrap: nowrap !important;
    gap: 7px !important;
}
.st-key-calc_root [class*="st-key-calc_value_area_"] div[data-testid="stColumn"] {
    flex: none !important;
    width: auto !important;
    min-width: 0 !important;
}
.st-key-calc_root [class*="st-key-calc_value_area_"] div[data-testid="stNumberInputContainer"] {
    width: 68px !important;
}

/* ── 세그먼트 컨트롤: 동그라미 완전 제거, 선택된 항목만 진초록 캡슐 ── */
.st-key-calc_root div[role="radiogroup"] {
    display: inline-flex !important;
    flex-wrap: nowrap !important;
    gap: 1px !important;
    background: #F1F3F0;
    border-radius: 8px;
    padding: 2px;
    width: fit-content;
    max-width: 100%;
}
.st-key-calc_root div[role="radiogroup"] label div:has(+ [data-testid="stMarkdownContainer"]) {
    display: none !important;
}
.st-key-calc_root div[role="radiogroup"] > label {
    border: none !important;
    background: transparent !important;
    padding: 5px 6px !important;
    border-radius: 6px !important;
    min-width: unset !important;
    height: 26px;
    box-sizing: border-box;
    flex: none;
}
.st-key-calc_root div[role="radiogroup"] > label p {
    font-size: .75rem !important;
    color: #6B756E !important;
    font-weight: 500 !important;
    white-space: nowrap;
}
.st-key-calc_root div[role="radiogroup"] > label:has(input:checked) {
    background: #11654C !important;
}
.st-key-calc_root div[role="radiogroup"] > label:has(input:checked) p {
    color: #fff !important;
    font-weight: 700 !important;
}

/* ── 숫자 입력창: 스태퍼(-/+) 제거, 세그먼트 버튼과 같은 높이로, 우측 정렬 ── */
.st-key-calc_root div[data-testid="stNumberInputStepUp"],
.st-key-calc_root div[data-testid="stNumberInputStepDown"] {
    display: none !important;
}
.st-key-calc_root div[data-testid="stNumberInputContainer"] {
    height: 30px !important;
    border-radius: 7px !important;
}
.st-key-calc_root div[data-testid="stNumberInput"] input {
    text-align: right !important;
    height: 30px !important;
    padding: 0 8px !important;
    font-size: .78rem !important;
}

/* ── 쿠폰 구성: 관리수수료율 표와 같은 테두리/헤더 톤 + 플랫한 인풋(표 안에 별도 박스로 안 보이게) ── */
.st-key-calc_coupon {
    border: 1px solid #E2E6E1;
    border-radius: 8px;
    overflow: hidden;
    width: 100%;
    gap: 0 !important;
    background: #FFFFFF;
}
.st-key-calc_coupon div[data-testid="stHorizontalBlock"] {
    padding: 6px 10px;
    border-bottom: 1px solid #EFF2EE;
    flex-wrap: nowrap !important;
    align-items: center !important;
}
.st-key-calc_coupon [class*="st-key-calc_coupon_row_"]:last-child div[data-testid="stHorizontalBlock"] {
    border-bottom: none;
}
.st-key-calc_coupon_header div[data-testid="stHorizontalBlock"] {
    background: #F8F9FA;
    border-bottom: 1px solid #E2E6E1;
    padding: 6px 10px;
}
.st-key-calc_coupon .calc-cpn-label { font-size: 13px; white-space: nowrap; text-align: left; }
.st-key-calc_coupon .calc-cpn-center { font-size: 13px; white-space: nowrap; text-align: center; }
.st-key-calc_coupon .calc-cpn-right { font-size: 13px; white-space: nowrap; text-align: right; }
.st-key-calc_coupon .calc-cpn-total { font-size: 13px; white-space: nowrap; text-align: right; font-weight: 700; color: #111827; }

/* 입력창: 배경/테두리를 최소화해 표 안에 또 다른 박스가 있는 것처럼 보이지 않게 한다 */
.st-key-calc_coupon div[data-testid="stNumberInputContainer"] {
    height: 32px !important; min-height: 32px !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 6px !important;
    background: #FFFFFF !important;
    box-shadow: none !important;
}
.st-key-calc_coupon div[data-testid="stNumberInput"] input {
    height: 32px !important; padding: 0 8px !important; font-size: 13px !important;
    background: transparent !important; border: none !important; box-shadow: none !important;
}

/* 수량: 칸 중앙 정렬 */
.st-key-calc_coupon [class*="st-key-calc_cpn_qty_"] { display: flex !important; justify-content: center !important; }
.st-key-calc_coupon [class*="st-key-calc_cpn_qty_"] div[data-testid="stNumberInputContainer"] { width: 56px !important; }
.st-key-calc_coupon [class*="st-key-calc_cpn_qty_"] div[data-testid="stNumberInput"] input { text-align: center !important; }

/* 단가: 입력창 + '원'을 한 줄(flex)로 붙여서 칸 우측 정렬 */
.st-key-calc_coupon [class*="st-key-calc_cpn_price_"] { display: flex !important; justify-content: flex-end !important; }
.st-key-calc_coupon [class*="st-key-calc_cpn_price_"] div[data-testid="stHorizontalBlock"] {
    justify-content: flex-end !important; align-items: center !important; gap: 4px !important;
    padding: 0 !important; border-bottom: none !important;
}
.st-key-calc_coupon [class*="st-key-calc_cpn_price_"] div[data-testid="stColumn"] {
    flex: none !important; width: auto !important; min-width: 0 !important;
}
.st-key-calc_coupon [class*="st-key-calc_cpn_price_"] div[data-testid="stNumberInputContainer"] { width: 64px !important; }
.st-key-calc_coupon [class*="st-key-calc_cpn_price_"] div[data-testid="stNumberInput"] input { text-align: right !important; }
.st-key-calc_coupon [class*="st-key-calc_cpn_price_"] .calc-unit { padding-left: 0; font-size: 13px; }

/* '기본값으로' 버튼: 쿠폰 구성 타이틀 라인의 가장 우측(표 오른쪽 끝과 일치)으로 정렬 */
.st-key-calc_root [class*="st-key-calc_text_btn"] {
    display: flex !important;
    align-items: flex-end !important;
    justify-content: flex-end !important;
}

/* 섹션1 좌/우 패널: 사이에 세로 구분선. 우측 패널은 여백을 spacer div로 직접 제어하므로
   패널 자체의 기본 gap은 0으로 둔다 */
.st-key-calc_root [class*="st-key-calc_section1_left_panel"] {
    border-right: 1px solid #E5E7EB;
    padding-right: 20px;
}
.st-key-calc_root [class*="st-key-calc_section1_right_panel"] {
    padding-left: 20px;
    gap: 0 !important;
}
/* 이 패널 바로 아래 놓인 st.markdown() 하나짜리 블록(제목/표)은 반드시 st.container(key=...)로
   감싸서 쓴다. 감싸지 않은 채 flex-column 패널의 '직속 자식'으로 두면, 그 stElementContainer의
   실제 렌더 높이가 안에 든 큰 폰트 콘텐츠 높이보다 훨씬 작게 잡혀(중첩 flex의 높이 계산 버그)
   바로 다음 요소와 겹쳐 보이는 문제가 있었다(container로 한 번 더 감싸면 정상 동작 확인).
   같은 이유로 margin-bottom도 안쪽 콘텐츠에 주면 반영되지 않아서, 대신 높이가 고정된
   '스페이서 컨테이너'를 별도 요소로 끼워 넣어 여백을 만든다. */
.st-key-calc_root [class*="st-key-calc_spacer_8a"],
.st-key-calc_root [class*="st-key-calc_spacer_8b"] {
    height: 8px !important; min-height: 8px !important; overflow: hidden;
}
.st-key-calc_root [class*="st-key-calc_spacer_24"] {
    height: 24px !important; min-height: 24px !important; overflow: hidden;
}
/* 섹션2 좌/우 패널: 섹션1과 좌우 패딩을 맞춰서 관리수수료율/쿠폰구성 표와
   현재 설정 통과 현황 카드의 좌우 끝선이 페이지 전체에서 세로로 일치하게 한다 */
.st-key-calc_root [class*="st-key-calc_section2_left_panel"] {
    padding-right: 20px;
}
.st-key-calc_root [class*="st-key-calc_section2_right_panel"] {
    padding-left: 20px;
}
.st-key-calc_root [class*="st-key-calc_section2_right_panel"] .ov-stats,
.st-key-calc_root [class*="st-key-calc_section2_right_panel"] .ov-stat {
    width: 100%;
    box-sizing: border-box;
}

/* ── 표(관리수수료율/공헌이익률/상세표): 이 표들은 이미 카드(st.container(border=True))
   안에 들어있으므로, 표 자체에 또 외곽 테두리를 그리면 "표 안에 표"처럼 이중으로 갇혀 보인다.
   그래서 표 바깥 테두리는 완전히 없애고, 셀 사이 은은한 안쪽 구분선만 남긴다 ── */
.st-key-calc_root .calc-table {
    font-size: 13px; width: 100%;
    border: none !important; outline: none !important;
    border-collapse: collapse;
}
.st-key-calc_root .calc-table thead th {
    padding: 8px 12px; vertical-align: middle;
    border-bottom: 1px solid #F0F0F0; border-right: 1px solid #F0F0F0;
}
.st-key-calc_root .calc-table thead th:last-child { border-right: none; }
.st-key-calc_root .calc-table tbody td {
    padding: 8px 12px; line-height: 1.3; vertical-align: middle;
    border-bottom: 1px solid #F0F0F0; border-right: 1px solid #F0F0F0;
}
.st-key-calc_root .calc-table tbody td:last-child { border-right: none; }
.st-key-calc_root .calc-table tbody tr:last-child td { border-bottom: none; }

/* 관리수수료율 표 / 공헌이익률 변화 표: 표 자체는 테두리 없이 카드 배경에 자연스럽게 채워지고,
   헤더 배경색만 살려서 표 영역을 구분한다 (외곽선은 카드 하나로 충분) */
.st-key-calc_root .calc-table-bordered {
    border: none !important;
    border-radius: 0;
    overflow: visible;
}
.st-key-calc_root .calc-table-bordered thead th {
    background: #F8F9FA;
}
</style>
"""


def render():
    _ensure_state()
    s = st.session_state
    coupon_cfg = _current_coupon()

    with st.container(key="calc_root"):
        st.markdown(_DENSE_CSS, unsafe_allow_html=True)

        top1, top2 = st.columns([4, 1])
        with top1:
            st.title(auth.PAGE_CALCULATOR)
        with top2:
            st.markdown('<div style="height:1.2rem"></div>', unsafe_allow_html=True)
            st.button("기본값으로 초기화", on_click=_reset_all, use_container_width=True)

        # ==== 섹션 1: 좌측(설정 4행 스택) + 우측(참조 표: 관리수수료율 + 쿠폰 구성) ====
        with st.container(border=True):
            st.markdown('<div class="ov-panel-title">상품 할인 · 유치수수료(R/S) · 관리수수료 설정</div>', unsafe_allow_html=True)

            card1_left, card1_right = st.columns(_SECTION_SPLIT)

            with card1_left:
                with st.container(key="calc_section1_left_panel"):
                    _mode_row("상품 할인", "calc_disc_mode", ["없음", "정률", "정액"], {"없음": "원", "정률": "%", "정액": "원"})
                    _mode_row("유치수수료(R/S)", "calc_acq_mode", ["정액", "정률", "표기준"], {"정액": "원", "정률": "%", "표기준": "%"})

                    st.markdown('<div class="calc-field-label">관리수수료</div>', unsafe_allow_html=True)
                    mc_rc, mc_vc = st.columns(_FIELD_SPLIT)
                    with mc_rc:
                        mgmt_mode = st.radio(
                            "관리수수료", ["표기준", "정률", "정액"],
                            key="calc_mgmt_mode", horizontal=True, label_visibility="collapsed",
                        )
                    with mc_vc:
                        unit = "원" if mgmt_mode == "정액" else "%p 인하"
                        with st.container(key="calc_value_area_calc_mgmt_mode"):
                            ic1, ic2, ic3, ic4 = st.columns([1, 1, 1, 1])
                            with ic1:
                                st.number_input(
                                    "관리수수료", key="calc_mgmt_value",
                                    step=1000 if unit == "원" else 1, label_visibility="collapsed",
                                )
                            with ic2:
                                st.markdown(f'<div class="calc-unit">{unit}</div>', unsafe_allow_html=True)
                            ic3.markdown('<div class="calc-unit">재계약:</div>', unsafe_allow_html=True)
                            with ic4:
                                st.radio(
                                    "재계약 시", ["낮춘 요율", "기존 요율"],
                                    key="calc_mgmt_renew_mode", horizontal=True, label_visibility="collapsed",
                                )

                    _mode_row("무료체험권", "calc_trial_mode", ["없음", "제공"], {"없음": "원", "제공": "원"})

            with card1_right:
                with st.container(key="calc_section1_right_panel"):
                    with st.container(key="calc_mgmt_title"):
                        st.markdown('<div class="calc-col-title">관리수수료율</div>', unsafe_allow_html=True)
                    with st.container(key="calc_spacer_8a"):
                        st.markdown("&nbsp;", unsafe_allow_html=True)

                    apply_cut = s["calc_mgmt_mode"] == "정률"
                    rows_html = []
                    for prod in ("Lite", "Basic", "Mega"):
                        cells = [f'<td class="product-cell">{prod}</td>']
                        for region_key in ("metro", "local"):
                            base = MGMT_BASE_RATE[prod][region_key]
                            now = max(0, base - abs(s["calc_mgmt_value"]) / 100) if apply_cut else base
                            cells.append(f"<td>{_compare_pct_cell(base, now, False, 0)}</td>")
                        rows_html.append(f"<tr>{''.join(cells)}</tr>")
                    with st.container(key="calc_mgmt_table"):
                        st.markdown(
                            '<div class="calc-table-scroll calc-table-bordered"><table class="calc-table">'
                            '<thead><tr><th>상품</th><th>수도권</th><th>지방</th></tr></thead>'
                            f"<tbody>{''.join(rows_html)}</tbody></table></div>",
                            unsafe_allow_html=True,
                        )
                    with st.container(key="calc_spacer_24"):
                        st.markdown("&nbsp;", unsafe_allow_html=True)

                    hdr_coupon = st.container(key="calc_hdr_row_coupon")
                    ch1, ch2 = hdr_coupon.columns([2.4, 1])
                    ch1.markdown(
                        '<div class="calc-col-title" style="white-space:nowrap;">쿠폰 구성 (6개월 기준·1년 계약은 자동 2배)</div>',
                        unsafe_allow_html=True,
                    )
                    with ch2:
                        with st.container(key="calc_text_btn_coupon"):
                            st.button("기본값으로", on_click=_reset_coupon, key="reset_coupon_btn")
                    with st.container(key="calc_spacer_8b"):
                        st.markdown("&nbsp;", unsafe_allow_html=True)

                    coupon_rows = [
                        ("Lite·일반", "calc_cpn_lite_general_qty", "calc_cpn_lite_general_price"),
                        ("Lite·집주인", "calc_cpn_lite_owner_qty", "calc_cpn_lite_owner_price"),
                        ("그외·일반", "calc_cpn_other_general_qty", "calc_cpn_other_general_price"),
                        ("그외·집주인", "calc_cpn_other_owner_qty", "calc_cpn_other_owner_price"),
                    ]
                    with st.container(key="calc_coupon"):
                        with st.container(key="calc_coupon_header"):
                            hc = st.columns([1.3, 0.8, 0.9, 1.1])
                            hc[0].markdown('<div class="calc-hint calc-cpn-label" style="font-weight:600;">쿠폰종류</div>', unsafe_allow_html=True)
                            hc[1].markdown('<div class="calc-hint calc-cpn-center" style="font-weight:600;">수량</div>', unsafe_allow_html=True)
                            hc[2].markdown('<div class="calc-hint calc-cpn-right" style="font-weight:600;">단가</div>', unsafe_allow_html=True)
                            hc[3].markdown('<div class="calc-hint calc-cpn-right" style="font-weight:600;">합계</div>', unsafe_allow_html=True)
                        for label, qty_key, price_key in coupon_rows:
                            with st.container(key=f"calc_coupon_row_{qty_key}"):
                                c1, c2, c3, c4 = st.columns([1.3, 0.8, 0.9, 1.1])
                                c1.markdown(f'<div class="calc-cpn-label">{label}</div>', unsafe_allow_html=True)
                                with c2:
                                    with st.container(key=f"calc_cpn_qty_{qty_key}"):
                                        st.number_input("수량", key=qty_key, min_value=0, step=1, label_visibility="collapsed")
                                with c3:
                                    with st.container(key=f"calc_cpn_price_{price_key}"):
                                        p1, p2 = st.columns([1.6, 1])
                                        with p1:
                                            st.number_input("단가", key=price_key, min_value=0, step=10, label_visibility="collapsed")
                                        with p2:
                                            st.markdown('<div class="calc-unit">원</div>', unsafe_allow_html=True)
                                total = s[qty_key] * s[price_key]
                                c4.markdown(f'<div class="calc-cpn-total">{_won(total)}</div>', unsafe_allow_html=True)

        # ==== 섹션 2: 좌측(공헌이익률 변화) + 우측(현재 설정 통과 현황 KPI) ====
        with st.container(border=True):
            sec2_left, sec2_right = st.columns(_SECTION_SPLIT)

            with sec2_left:
                with st.container(key="calc_section2_left_panel"):
                    hdr_grid = st.container(key="calc_hdr_row_grid")
                    gh1, gh2 = hdr_grid.columns([1.6, 1])
                    gh1.markdown('<div class="calc-col-title">공헌이익률(신규) 변화</div>', unsafe_allow_html=True)
                    with gh2:
                        with st.container(key="calc_term_right_grid"):
                            st.radio("기간", ["6개월", "1년"], key="calc_grid_term", horizontal=True, label_visibility="collapsed")

                    grid_rows = []
                    for prod in ("Lite", "Basic", "Mega"):
                        cells = [f'<td class="product-cell">{prod}</td>']
                        for g in DATA:
                            row = next(r for r in g["rows"] if r["term"] == s["calc_grid_term"] and r["product"] == prod)
                            c = _compute_row(row, s, coupon_cfg)
                            delta_pct = (c["rate_new"] - c["floor"]) * 100
                            text = f"{delta_pct:+.1f}%p"
                            cls = "good" if c["pass"] else "bad"
                            cells.append(f'<td class="calc-grid-cell {cls}">{text}</td>')
                        grid_rows.append(f"<tr>{''.join(cells)}</tr>")
                    st.markdown(
                        '<div class="calc-table-scroll calc-table-bordered"><table class="calc-table">'
                        '<thead><tr><th>상품</th><th>수도권</th><th>부산경남</th><th>대구경북</th><th>호남제주</th></tr></thead>'
                        f"<tbody>{''.join(grid_rows)}</tbody></table></div>",
                        unsafe_allow_html=True,
                    )

            with sec2_right:
                with st.container(key="calc_section2_right_panel"):
                    # 옆의 공헌이익률 표와 같은 기간(6개월/1년) 토글을 기준으로 계산해 한 세트로 보여준다
                    six_mo_rows = [r for g in DATA for r in g["rows"] if r["term"] == "6개월"]
                    safe_max_acq_pct = min(_compute_row(r, s, coupon_cfg)["max_acq_pct"] for r in six_mo_rows)

                    term_rows = [(g["region"], r) for g in DATA for r in g["rows"] if r["term"] == s["calc_grid_term"]]
                    term_computed = [_compute_row(r, s, coupon_cfg) for _, r in term_rows]
                    passed_count = sum(1 for c in term_computed if c["pass"])
                    total_count = len(term_computed)
                    pass_sub = "전구간 가능" if passed_count == total_count else f"{total_count - passed_count}개 구간 불가"

                    tightest_idx = min(range(len(term_computed)), key=lambda i: term_computed[i]["max_acq_won"])
                    tightest_region, tightest_row = term_rows[tightest_idx]
                    tightest = term_computed[tightest_idx]

                    # 타이틀·보조 지표를 전부 같은 .ov-stat 박스 안에 넣어서, 카드 테두리 밖으로
                    # 글자가 넘치거나(잘림) 타이틀이 카드 안/밖에 중복 표시되는 일이 없게 한다.
                    pass_cls = "open" if passed_count == total_count else "close"
                    kpi_html = (
                        f'<div class="ov-stats" style="grid-template-columns:1fr;">'
                        f'<div class="ov-stat {pass_cls}" style="text-align:left;">'
                        f'<div class="label">현재 설정 통과 현황</div>'
                        f'<div class="value">{passed_count} / {total_count}</div>'
                        f'<div class="delta">{s["calc_grid_term"]} 기준 · {pass_sub}</div>'
                        f'<div style="font-size:13px; color:#6B756E; line-height:1.6; margin-top:10px; padding-top:10px; border-top:1px solid #EFF2EE;">'
                        f"6개월 안전 최대 유치수수료(R/S): <b>{_pct(safe_max_acq_pct)}</b><br>"
                        f"가장 타이트한 구간 최대 R/S 지급액: <b>{_won(tightest['max_acq_won'])}</b> "
                        f"({tightest_region} · {tightest_row['product']})"
                        f"</div>"
                        f"</div>"
                        f"</div>"
                    )
                    st.markdown(kpi_html, unsafe_allow_html=True)

        # ---- 상세 표 ----
        with st.container(border=True):
            hdr_detail = st.container(key="calc_hdr_row_detail")
            th1, th2 = hdr_detail.columns([3, 1])
            th1.markdown('<div class="calc-col-title" style="font-size:1.02rem;">지역 4개 × 상품 3개 = 12개 조합</div>', unsafe_allow_html=True)
            with th2:
                with st.container(key="calc_term_right_detail"):
                    st.radio("기간", ["6개월", "1년"], key="calc_term", horizontal=True, label_visibility="collapsed")

            rows_html = []
            for g in DATA:
                rows = [r for r in g["rows"] if r["term"] == s["calc_term"]]
                i = 0
                while i < len(rows):
                    j = i
                    while j + 1 < len(rows) and rows[j + 1]["disc"] == rows[i]["disc"]:
                        j += 1
                    span = j - i + 1
                    for k in range(i, j + 1):
                        row = rows[k]
                        c = _compute_row(row, s, coupon_cfg)
                        cells = []
                        if k == i:
                            cells.append(
                                f'<td class="region-cell" rowspan="{span}">{g["region"]}'
                                f'<span class="disc">({round(row["disc"] * 100)}%)</span></td>'
                            )
                        cells.append(f'<td class="product-cell">{row["product"]}</td>')
                        cells.append(f'<td>{_compare_cell(c["P"], c["Psold"], True)}</td>')
                        cells.append(f'<td>{_compare_cell(c["acq_baseline"], c["acq"])}</td>')
                        cells.append(f'<td>{_compare_cell(c["mgmt_baseline"], c["mgmt"])}</td>')
                        cells.append(f'<td>{_compare_cell(c["coupon_baseline"], c["coupon"])}</td>')
                        cells.append(f'<td>{_won(c["pg"])}</td>')
                        cells.append(f'<td>{_won(c["margin_new"])}</td>')
                        cells.append(f'<td>{_won(c["margin_renew"])}</td>')
                        cells.append(f'<td>{_compare_pct_cell(c["floor"], c["rate_new"], True)}</td>')
                        cells.append(f'<td>{_compare_pct_cell(c["floor_renew"], c["rate_renew"], True)}</td>')
                        pill_cls, pill_text = ("pass", "가능") if c["pass"] else ("fail", "불가")
                        cells.append(f'<td><span class="calc-pill {pill_cls}">{pill_text}</span></td>')
                        rows_html.append(f"<tr>{''.join(cells)}</tr>")
                    i = j + 1

            st.markdown(
                '<div class="calc-table-scroll"><table class="calc-table">'
                "<thead><tr>"
                "<th>지역</th><th>상품</th><th>상품가</th><th>유치수수료(R/S)</th><th>관리수수료</th>"
                "<th>쿠폰비용</th><th>PG수수료</th><th>공헌이익(신규)</th><th>공헌이익(재계약)</th>"
                "<th>공헌이익률(신규)</th><th>공헌이익률(재계약)</th><th>판정</th>"
                "</tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody></table></div>",
                unsafe_allow_html=True,
            )
