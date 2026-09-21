# -*- coding: utf-8 -*-
"""네이버 CP 현황 메뉴의 집계 레이어.

원본(시트 rawdata, 약 68,000행)을 한 번 읽어서 월 x CP 축의 지표 묶음으로 만들어 둔다.
원본은 Supabase에 둔다(cp_store) — 저장소가 공개라 엑셀을 git에 넣을 수 없고,
Streamlit Cloud는 재배포마다 파일시스템이 초기화되기 때문이다. 로컬에 엑셀이 있고
DB가 비어 있으면 엑셀로 대신 읽는다(개발용). industry_market_stats.py / real_estate_stats.py와
같은 역할(화면은 pages_content/cp_status.py가 그린다).

── 이 데이터의 함정 (여기를 잘못 다루면 숫자가 통째로 어긋난다) ─────────────
 1) 총계 행은 `매물그룹 == '전체'`로만 판별한다. 시도로 거르면 안 된다.
    (2026-06 한공협 총계 행은 시도가 NaN이라, 시도=='전체'로 거르면 그 달이 결측으로
     빠지는 동시에 상세합에도 섞여 매물수가 2배가 된다.)
 2) 상세 행 = 그 외 전부. 입도 = 시도 x 구시군 x 매물그룹(3종).
 3) 매물수는 가산 가능 — 상세합 == 총계 (전 월·전 CP 오차 0). validate()에서 검증한다.
 4) 회원수는 가산 불가 — 한 회원이 여러 지역·유형·검증방식에 중복 계상되어 상세합이
    총계의 1.2~4.8배. 회원 점유율은 반드시 총계 행에서만 계산한다.
 5) 회원수는 CP별로 각각 책정된다(같은 중개사가 2개 CP를 쓰면 양쪽에 1명씩)
    → 합계는 고유 중개사무소 수가 아니라 'CP 계약 건수'다.
 6) 시점 8개, 수집일이 월말이 아니고 제각각. 연월구분에 2026-08이 없어 2026-09를 '8월'로 쓴다.
 7) 2026-05 총계 행은 검증방식 18개 컬럼이 전부 NaN → 매물수는 상세합으로 복원하고
    (다른 달로 검산하면 오차 0), 회원수는 중복 계상 때문에 복원이 불가능하므로 None.
 8) 한공협은 전 기간 검증방식 데이터가 없다(지역·매물유형만 존재).
 9) 전화확인은 2026-03부터 0건, 사전매물은 전 기간 0건 → 실질 7종.
10) 114는 2026-04부터 행 자체가 없다(결측이 아니라 시장 퇴출) → 마지막 관측 이후는 0으로 본다.
11) CP변환2에 int 114가 섞여 있어 astype(str)이 필수다.
12) 권역은 권역구분=='수도권'이면 수도권, 그 외 전부 지방.
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

import cp_store

XLSX_NAME = "네이버CP 현황_rawdata.xlsx"
SHEET = "rawdata"

_HERE = os.path.dirname(os.path.abspath(__file__))
# 앞에서부터 먼저 존재하는 파일을 쓴다. 평소엔 OneDrive 원본을 그대로 보고,
# 다른 PC/서버에서 돌릴 땐 data/ 밑에 복사해두면 된다.
SRC_CANDIDATES = [
    os.path.join(os.path.expanduser("~"), "OneDrive - 프롭티어", "바탕 화면",
                 "realtor-dashboard", "cp", XLSX_NAME),
    os.path.join(_HERE, "data", XLSX_NAME),
]

# 검증방식 9종. 컬럼명 규칙은 '<방식>매물수' / '<방식>회원수'.
METHODS = ["현장확인", "홍보확인서", "홍보확인서2", "전화확인", "신홍보확인서",
           "모바일", "모바일v2", "사전매물", "현장확인v2"]
# 파생 지표 — 매물수만 존재한다(회원수는 중복 계상이라 정의되지 않음).
# '로켓 타겟'(3종)과 원자료의 '집주인프로모션'(4종)은 다르다 — 후자는 현장확인이 더 들어간다.
# 원자료의 집주인프로모션매물 / 모바일12매물 / 구홍보전화매물 컬럼과 아래 조합이 정확히 일치함을 확인했다.
DERIVED = {
    "로켓 타겟": ["신홍보확인서", "모바일", "모바일v2"],
    "집주인프로모션": ["현장확인", "신홍보확인서", "모바일", "모바일v2"],
    "구홍보전화": ["홍보확인서", "홍보확인서2", "전화확인"],
    "모바일12": ["모바일", "모바일v2"],
}
# 지역별 분석의 기본 기준 지표.
OWNER = "로켓 타겟"
GROUPS = ["공동주택", "비공동주택", "비공동비주택"]
ZONES = ["수도권", "지방"]
# 시도 표시 순서 — 가나다순이 아니라 수도권 우선·물량 순(사용자 지정)으로 본다.
# sidos가 sl/sm/vs 격자의 축이라 여기서 한 번 정하면 화면 전체가 같은 순서를 쓴다.
SIDO_ORDER = ["서울", "경기", "인천", "세종", "충남", "부산", "울산", "충북", "대전",
              "대구", "강원", "광주", "경북", "전남", "경남", "전북", "제주"]

HANGONG = "한공협"
PROPTIER = "프롭티어"
PROPTIER_PARTS = ["이실장", "매경"]

# 연월구분 -> 화면 라벨. 2026-08이 없어서 2026-09를 '8월'로 붙이고 수집일을 함께 표기한다(함정 6).
MONTH_LABEL = {
    "2026-01": "1월", "2026-02": "2월", "2026-03": "3월", "2026-04": "4월",
    "2026-05": "5월", "2026-06": "6월", "2026-07": "7월", "2026-09": "8월",
}


def source_path() -> str | None:
    for p in SRC_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


# ── 작은 유틸 ────────────────────────────────────────────────────────────────
def _n(x):
    """NaN/None -> None, 그 외엔 float. 정수로 떨어지면 int."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    r = round(f)
    return int(r) if abs(f - r) < 1e-9 else f


def nz(x):
    """None을 0으로 보는 합산용 변환."""
    return 0 if x is None else x


def add(a, b):
    """None을 '없음'으로 보는 덧셈. 둘 다 None이면 None (합산 시 데이터 없음을 보존)."""
    if a is None:
        return b
    if b is None:
        return a
    return a + b


def _merge(vals):
    """같은 모양의 중첩 리스트/스칼라들을 add()로 합친다 (프롭티어 = 이실장 + 매경)."""
    head = vals[0]
    if head is None or isinstance(head, (int, float)):
        out = None
        for v in vals:
            out = add(out, v)
        return out
    return [_merge([v[i] for v in vals]) for i in range(len(head))]


# ── 로딩 ─────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="네이버 CP 원자료를 집계하는 중…")
def load(version: str) -> dict:
    """원본 -> 집계 dict. version을 인자로 받는 이유는 원본이 갱신되면 캐시가 깨지게 하려고."""
    df = _read_source(version)
    # 함정 11: CP변환2에 int 114가 섞여 있다. 문자열 축은 전부 astype(str)로 고정.
    for c in ["CP변환2", "매물그룹", "연월구분", "시도", "구시군", "권역구분"]:
        df[c] = df[c].astype(str)
    df["div_date"] = df["div_date"].astype(str).str.slice(0, 10)

    # 함정 1·2: 총계/상세 분리는 오직 매물그룹으로 한다.
    tot = df[df["매물그룹"] == "전체"]
    det = df[df["매물그룹"] != "전체"].copy()
    # 함정 12
    det["권역"] = det["권역구분"].where(det["권역구분"] == "수도권", "지방")

    months = sorted(df["연월구분"].unique())
    mi = {m: i for i, m in enumerate(months)}
    nm = len(months)
    dates = [sorted(df.loc[df["연월구분"] == m, "div_date"].unique())[0] for m in months]
    labels = [MONTH_LABEL.get(m, m[-2:].lstrip("0") + "월") for m in months]

    cps = sorted(df["CP변환2"].unique())
    # 목록에 없는 시도명이 들어와도 떨어뜨리지 않고 뒤에 가나다순으로 붙인다.
    sidos = sorted(det["시도"].unique(),
                   key=lambda s: (SIDO_ORDER.index(s), "") if s in SIDO_ORDER
                   else (len(SIDO_ORDER), s))
    si = {s: i for i, s in enumerate(sidos)}
    gi = {g: i for i, g in enumerate(GROUPS)}
    zi = {z: i for i, z in enumerate(ZONES)}
    vl = [v + "매물수" for v in METHODS]
    vm = [v + "회원수" for v in METHODS]

    def grid(*sizes):
        def mk(rest):
            return None if not rest else [mk(rest[1:]) for _ in range(rest[0])]
        return [mk(sizes) for _ in range(nm)]

    D = {cp: {
        "l": [None] * nm, "m": [None] * nm, "dm": [None] * nm,
        "sl": grid(len(sidos)), "sm": grid(len(sidos)),
        "gl": grid(len(GROUPS)), "gm": grid(len(GROUPS)),
        "zl": grid(len(ZONES)), "zm": grid(len(ZONES)),
        "vl": grid(len(METHODS)), "vm": grid(len(METHODS)),
        "vz": grid(len(ZONES), len(METHODS)),
        "vs": grid(len(sidos), len(METHODS)),
    } for cp in cps}

    # 총계 행 -> 매물수 / 회원수 (함정 4: 회원 점유율은 오직 여기서만 나온다)
    for (m, cp), r in tot.set_index(["연월구분", "CP변환2"]).iterrows():
        D[cp]["l"][mi[m]] = _n(r["매물수"])
        D[cp]["m"][mi[m]] = _n(r["회원수"])

    # 상세 행 회원 합 — 실제 회원수가 아니라 '커버 배수'(중복 계상 정도)를 보기 위한 값이다.
    for (m, cp), v in det.groupby(["연월구분", "CP변환2"])["회원수"].sum().items():
        D[cp]["dm"][mi[m]] = _n(v)

    # 지역 / 매물그룹 / 권역 — 전부 상세 행 기준
    for (m, cp, s), r in det.groupby(["연월구분", "CP변환2", "시도"])[["매물수", "회원수"]].sum().iterrows():
        D[cp]["sl"][mi[m]][si[s]] = _n(r["매물수"])
        D[cp]["sm"][mi[m]][si[s]] = _n(r["회원수"])
    for (m, cp, g), r in det.groupby(["연월구분", "CP변환2", "매물그룹"])[["매물수", "회원수"]].sum().iterrows():
        D[cp]["gl"][mi[m]][gi[g]] = _n(r["매물수"])
        D[cp]["gm"][mi[m]][gi[g]] = _n(r["회원수"])
    for (m, cp, z), r in det.groupby(["연월구분", "CP변환2", "권역"])[["매물수", "회원수"]].sum().iterrows():
        D[cp]["zl"][mi[m]][zi[z]] = _n(r["매물수"])
        D[cp]["zm"][mi[m]][zi[z]] = _n(r["회원수"])

    # 검증방식 — 총계 행 기준.
    # 함정 7: 2026-05 총계 행은 전부 NaN이라 매물수만 상세합으로 복원한다. 회원수는 중복 때문에 불가 -> None.
    det_vl = det.groupby(["연월구분", "CP변환2"])[vl].sum(min_count=1)
    restored = []
    for (m, cp), r in tot.set_index(["연월구분", "CP변환2"]).iterrows():
        row = [_n(r[c]) for c in vl]
        if all(x is None for x in row) and (m, cp) in det_vl.index:
            d = det_vl.loc[(m, cp)]
            cand = [_n(d[c]) for c in vl]
            if any(x is not None for x in cand):
                row = cand
                restored.append((m, cp))
        D[cp]["vl"][mi[m]] = row
        D[cp]["vm"][mi[m]] = [_n(r[c]) for c in vm]

    # 검증방식 x 권역 / x 시도 교차표는 상세 행에서만 만들 수 있다.
    # (매물수는 가산 가능해서 시도별로 쪼갠 합이 총계와 정확히 맞는다 — validate()에서 검증한다.
    #  회원수는 한 회원이 여러 지역에 중복 계상돼 지역별로 쪼개면 쓸 수 없으므로 아예 만들지 않는다.)
    for (m, cp, z), r in det.groupby(["연월구분", "CP변환2", "권역"])[vl].sum(min_count=1).iterrows():
        D[cp]["vz"][mi[m]][zi[z]] = [_n(r[c]) for c in vl]
    for (m, cp, s_), r in det.groupby(["연월구분", "CP변환2", "시도"])[vl].sum(min_count=1).iterrows():
        D[cp]["vs"][mi[m]][si[s_]] = [_n(r[c]) for c in vl]

    # 함정 10: 마지막 관측 이후는 결측이 아니라 '시장 퇴출' -> 0으로 채운다.
    # (한공협 검증방식처럼 행은 있는데 값만 없는 경우는 None 그대로 둬야 하므로,
    #  '그 달에 행 자체가 있었는지'를 기준으로 판단한다.)
    seen = df.groupby("CP변환2")["연월구분"].apply(lambda s: {mi[x] for x in s}).to_dict()
    for cp in cps:
        last = max(seen[cp])
        for i in range(last + 1, nm):
            d = D[cp]
            d["l"][i] = d["m"][i] = d["dm"][i] = 0
            for k, w in (("sl", len(sidos)), ("sm", len(sidos)), ("gl", len(GROUPS)),
                         ("gm", len(GROUPS)), ("zl", len(ZONES)), ("zm", len(ZONES)),
                         ("vl", len(METHODS)), ("vm", len(METHODS))):
                d[k][i] = [0] * w
            d["vz"][i] = [[0] * len(METHODS) for _ in ZONES]
            d["vs"][i] = [[0] * len(METHODS) for _ in sidos]

    # 프롭티어 = 이실장 + 매경 합산. 회원수는 함정 5대로 'CP 계약 건수' 합이라 더해도 된다.
    D[PROPTIER] = {k: _merge([D[p][k] for p in PROPTIER_PARTS]) for k in D[PROPTIER_PARTS[0]]}

    # 함정 9: 전 기간·전 CP 합이 0인 방식은 실질적으로 죽은 방식이다.
    vsum = [0.0] * len(METHODS)
    for cp in cps:
        for row in D[cp]["vl"]:
            for j, x in enumerate(row):
                vsum[j] += nz(x)
    methods_active = [METHODS[j] for j in range(len(METHODS)) if vsum[j] > 0]
    # 전화확인이 마지막으로 잡힌 달 (화면 주석에 실제 수치를 쓰기 위해)
    jp = METHODS.index("전화확인")
    phone_last = None
    for i, m in enumerate(months):
        if sum(nz(D[cp]["vl"][i][jp]) for cp in cps) > 0:
            phone_last = m
    dead = [METHODS[j] for j in range(len(METHODS)) if vsum[j] == 0]

    cover = [D[cp]["dm"][i] / D[cp]["m"][i]
             for cp in cps for i in range(nm) if D[cp]["m"][i] and D[cp]["dm"][i]]

    # 시군구 단위는 격자로 만들면 40만 칸인데 실제로 값이 있는 건 그 60%뿐이라, 표를 그릴 때만
    # 잘라 쓰도록 DataFrame 그대로 싣는다. 구시군 이름은 시도가 달라도 겹치므로(동구가 6개 시도에
    # 존재) 반드시 (시도, 구시군) 쌍으로 다뤄야 한다.
    gu = (det.groupby(["연월구분", "CP변환2", "시도", "구시군"], as_index=False)
             [["매물수"] + vl].sum(min_count=1))
    gu[vl] = gu[vl].fillna(0)

    # 함정 1의 근거: 총계 행은 '월 x CP당 정확히 1행'이어야 한다.
    pairs = int(df.groupby(["연월구분", "CP변환2"]).ngroups)
    dup = int(tot.duplicated(["연월구분", "CP변환2"]).sum())

    out = {
        "months": months, "labels": labels, "dates": dates, "nm": nm,
        "cps": cps, "sidos": sidos, "groups": GROUPS, "zones": ZONES,
        "methods": METHODS, "methods_active": methods_active, "derived": DERIVED,
        "d": D, "gu": gu,
        "sido_of": det.groupby("시도")["구시군"].agg(lambda s: sorted(set(s))).to_dict(),
        "zone_of": det.drop_duplicates("시도").set_index("시도")["권역"].to_dict(),
        "meta": {
            "rows": int(len(df)), "tot_rows": int(len(tot)), "det_rows": int(len(det)),
            "pairs": pairs, "dup_tot": dup,
            "restored_months": sorted({m for m, _ in restored}),
            "phone_last": phone_last, "dead_methods": dead,
            "cover_min": round(min(cover), 2) if cover else None,
            "cover_max": round(max(cover), 2) if cover else None,
            "gone": [cp for cp in cps if D[cp]["l"][-1] == 0 and nz(D[cp]["l"][0]) > 0],
            "no_method": [cp for cp in cps
                          if all(x is None for row in D[cp]["vl"] for x in row)],
            "source": ("Supabase · cp_raw" if version.startswith("db:")
                       else os.path.basename(source_path() or XLSX_NAME)),
        },
    }
    # assert는 여기서 딱 한 번 돈다 — load()가 캐시되므로 화면을 조작할 때마다 다시 돌지 않는다.
    out["meta"]["validation"] = validate(out)
    return out


@st.cache_data(ttl=30, show_spinner=False)
def data_version() -> str | None:
    """원본 버전 문자열(= load의 캐시 키). DB에 적재본이 있으면 그걸 쓰고, 없으면 로컬
    엑셀을 본다. 둘 다 없으면 None — 화면은 '원본을 올려주세요' 안내를 띄운다.

    ttl을 30초로 둔 이유: 이 함수는 Supabase에 새 커넥션을 열어 150ms쯤 걸리는데,
    Streamlit은 위젯을 누를 때마다 전체를 다시 실행한다. 캐시가 없으면 클릭할 때마다
    그만큼 느려진다. 반대로 영구 캐시로 두면 다른 서버에서 올린 새 원본을 못 본다.
    30초면 클릭 비용은 0에 수렴하고, 업로드는 30초 안에 모든 서버에 퍼진다."""
    try:
        v = cp_store.version()
    except Exception:
        v = None          # DB에 닿지 못해도 로컬 엑셀이 있으면 볼 수 있게 한다
    if v:
        return "db:" + v
    p = source_path()
    return f"xlsx:{p}:{os.path.getmtime(p)}" if p else None


def _read_source(version: str) -> pd.DataFrame:
    if version.startswith("db:"):
        return cp_store.read_all()
    return pd.read_excel(source_path(), sheet_name=SHEET, engine="openpyxl")


def load_default() -> dict | None:
    v = data_version()
    return load(v) if v else None


# ── 조회 헬퍼 ────────────────────────────────────────────────────────────────
def market_cps(D: dict, include_hangong: bool) -> list:
    """분모(시장 전체)에 넣을 CP 목록. 프롭티어는 이실장·매경의 합성이라 분모에서 제외한다."""
    return [c for c in D["cps"] if include_hangong or c != HANGONG]


def market(D: dict, key: str, i: int, include_hangong: bool):
    """월 i의 시장 합계. key는 'l'(매물수) 또는 'm'(회원수)."""
    return sum(nz(D["d"][c][key][i]) for c in market_cps(D, include_hangong))


def market_vec(D: dict, key: str, i: int, include_hangong: bool, width: int) -> list:
    """월 i의 시장 합계를 벡터 축(sl/gl/zl/vl…)으로. None은 0으로 본다."""
    out = [0.0] * width
    for c in market_cps(D, include_hangong):
        row = D["d"][c][key][i] or []
        for j, x in enumerate(row):
            out[j] += nz(x)
    return out


def series(D: dict, cp: str, key: str) -> list:
    return D["d"][cp][key]


def share_series(D: dict, cp: str, key: str, include_hangong: bool) -> list:
    """월별 점유율(%) 시계열. 분모가 0이면 None."""
    out = []
    for i in range(D["nm"]):
        tot = market(D, key, i, include_hangong)
        v = D["d"][cp][key][i]
        out.append(None if (not tot or v is None) else v / tot * 100)
    return out


def per_member(D: dict, cp: str) -> list:
    """회원당 매물수. 회원수가 0/None이면 None."""
    d = D["d"][cp]
    return [None if not d["m"][i] or d["l"][i] is None else d["l"][i] / d["m"][i]
            for i in range(D["nm"])]


def cover_series(D: dict, cp: str) -> list:
    """커버 배수 = 상세합 회원수 / 총계 회원수. 1보다 클수록 지역·유형 중복 계상이 심하다."""
    d = D["d"][cp]
    return [None if not d["m"][i] or not d["dm"][i] else d["dm"][i] / d["m"][i]
            for i in range(D["nm"])]


NATION = "전체"


def region_options(D: dict) -> list:
    """지역 필터의 선택지. 전체 -> 권역 2개 -> 시도 17개."""
    return [NATION] + list(ZONES) + list(D["sidos"])


def sidos_in(D: dict, scope: str) -> list:
    """선택한 지역 범위에 들어가는 시도 목록."""
    if scope == NATION:
        return list(D["sidos"])
    if scope in ZONES:
        return [s for s in D["sidos"] if D["zone_of"].get(s) == scope]
    return [scope] if scope in D["sidos"] else []


def district_rows(D: dict, cps: list, i: int, scope: str):
    """(시도, 구시군)별 매물수와 검증방식 벡터를 DataFrame으로. cps에 여러 CP를 주면 합산한다.

    매물수는 가산 가능하므로 시군구 합 == 시도 합 == 총계다(validate에서 확인). 회원수는
    지역으로 쪼개면 중복 계상이라 여기 없다.
    """
    gu = D["gu"]
    sel = gu[(gu["연월구분"] == D["months"][i]) & (gu["CP변환2"].isin(cps))]
    keep = sidos_in(D, scope)
    if scope != NATION:
        sel = sel[sel["시도"].isin(keep)]
    cols = ["매물수"] + [v + "매물수" for v in METHODS]
    return sel.groupby(["시도", "구시군"], as_index=False)[cols].sum()


def method_vec(D: dict, cp: str, i: int, region: str = NATION) -> list:
    """시점 i, 지역 region에서 cp의 검증방식별 매물수 벡터(9칸).

    전국은 총계 행 기준(2026-05은 상세합으로 복원된 값), 권역·시도는 상세 행 기준이다.
    둘의 합은 정확히 같다(validate에서 검증) — 지역을 좁혔다고 총량이 달라지지 않는다.
    """
    d = D["d"][cp]
    if region == NATION:
        return d["vl"][i] or [None] * len(METHODS)
    if region in ZONES:
        return (d["vz"][i] or [None])[ZONES.index(region)] or [None] * len(METHODS)
    if region in D["sidos"]:
        return (d["vs"][i] or [None])[D["sidos"].index(region)] or [None] * len(METHODS)
    raise ValueError(f"알 수 없는 지역: {region}")


def method_market(D: dict, i: int, include_hangong: bool, region: str = NATION) -> list:
    """시점 i, 지역 region의 시장 전체 검증방식별 매물수."""
    out = [0.0] * len(METHODS)
    for c in market_cps(D, include_hangong):
        for j, v in enumerate(method_vec(D, c, i, region)):
            out[j] += nz(v)
    return out


def listings_at(D: dict, cp: str, i: int, region: str = NATION):
    """시점 i, 지역 region에서 cp의 전체 매물수(검증방식 구분 없이)."""
    d = D["d"][cp]
    if region == NATION:
        return d["l"][i]
    if region in ZONES:
        return (d["zl"][i] or [None])[ZONES.index(region)]
    return (d["sl"][i] or [None])[D["sidos"].index(region)]


def derived_at(D: dict, cp: str, i: int, region: str = NATION) -> dict:
    """파생 지표를 지역 단위로. 구성 방식이 전부 None이면 None(= 자료 없음)."""
    row = method_vec(D, cp, i, region)
    out = {}
    for name, parts in DERIVED.items():
        vals = [row[METHODS.index(p)] for p in parts]
        out[name] = None if all(v is None for v in vals) else sum(nz(v) for v in vals)
    return out


def derived_values(D: dict, cp: str, i: int) -> dict:
    """파생 3지표(매물수만). 구성 방식이 전부 None이면 None."""
    row = D["d"][cp]["vl"][i]
    out = {}
    for name, parts in DERIVED.items():
        vals = [row[METHODS.index(p)] for p in parts]
        out[name] = None if all(v is None for v in vals) else sum(nz(v) for v in vals)
    return out


def validate(D: dict) -> list:
    """함정들이 실제로 지켜졌는지 assert로 확인하고, 사람이 읽을 검증 로그를 돌려준다."""
    log = []
    nm, cps = D["nm"], D["cps"]
    mm = D["meta"]

    # 함정 1: 총계 행은 월 x CP당 정확히 1행 (시도로 걸렀다면 여기서 깨진다)
    assert mm["dup_tot"] == 0, "총계 행이 월 x CP당 2행 이상입니다"
    assert mm["tot_rows"] == mm["pairs"], (
        f"총계 행 {mm['tot_rows']}개 != 월 x CP 조합 {mm['pairs']}개")
    log.append(f"총계 행 {mm['tot_rows']}개 · 월 x CP 조합 {mm['pairs']}개와 1:1 일치")

    # 함정 3: 매물수는 가산 가능 -> 상세합 == 총계 (오차 0)
    worst = 0
    for c in cps:
        for i in range(nm):
            t = D["d"][c]["l"][i]
            s = sum(nz(x) for x in (D["d"][c]["sl"][i] or []))
            g = sum(nz(x) for x in (D["d"][c]["gl"][i] or []))
            z = sum(nz(x) for x in (D["d"][c]["zl"][i] or []))
            if t is None:
                continue
            worst = max(worst, abs(t - s), abs(t - g), abs(t - z))
    assert worst == 0, f"상세합과 총계가 어긋납니다 (최대 오차 {worst})"
    log.append("상세합 == 총계 (시도·매물그룹·권역 3축 모두 오차 0)")

    # 점유율 합 100%
    for inc in (True, False):
        for i in range(nm):
            tot = market(D, "l", i, inc)
            if not tot:
                continue
            s = sum(nz(D["d"][c]["l"][i]) for c in market_cps(D, inc)) / tot * 100
            assert abs(s - 100) < 1e-6, f"점유율 합이 100%가 아닙니다 ({s})"
    log.append("매물 점유율 합 = 100% (한공협 포함/제외 각각, 전 시점)")

    # 프롭티어 = 이실장 + 매경
    for i in range(nm):
        a = sum(nz(D["d"][p]["l"][i]) for p in PROPTIER_PARTS)
        assert nz(D["d"][PROPTIER]["l"][i]) == a, "프롭티어 합산이 어긋납니다"
    log.append("프롭티어 = 이실장 + 매경 합산 일치")

    # 검증방식을 시도·권역으로 쪼갠 합이 전국 값과 같아야 한다 (지역 필터의 전제)
    worst = 0
    for c in cps:
        for i in range(nm):
            nat = D["d"][c]["vl"][i] or []
            for axis, names in (("vs", D["sidos"]), ("vz", ZONES)):
                grid_ = D["d"][c][axis][i] or []
                for j in range(len(METHODS)):
                    s = sum(nz(row[j]) for row in grid_ if row)
                    n = nat[j] if j < len(nat) else None
                    if n is not None:
                        worst = max(worst, abs(n - s))
    assert worst == 0, f"검증방식 지역 분해가 전국 합과 어긋납니다 (최대 오차 {worst})"
    log.append("검증방식 지역 분해 == 전국 합 (시도·권역 모두 오차 0)")

    log.append(f"회원 커버 배수 {mm['cover_min']}~{mm['cover_max']}배 (회원수 가산 불가 근거)")
    if mm["restored_months"]:
        log.append("검증방식 매물수 복원: " + ", ".join(mm["restored_months"]) + " (총계 NaN -> 상세합)")
    return log
