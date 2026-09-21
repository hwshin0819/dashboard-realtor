# -*- coding: utf-8 -*-
"""네이버 CP 원본(rawdata)의 보관소.

Streamlit Cloud는 재배포마다 파일시스템이 초기화되고 저장소는 공개라, 원본 엑셀을
git에 넣을 수 없다. 그래서 다른 수집 자료와 똑같이 Supabase에 둔다(db.py).

집계는 cp_stats가 한다. 여기는 '읽고 쓰기'만 담당한다.
"""
from __future__ import annotations

import pandas as pd

import db

TABLE = "cp_raw"

# 엑셀 rawdata 시트의 컬럼 순서 그대로. 화면 로직이 이 이름들을 그대로 쓰므로
# 이름을 바꾸지 않고 큰따옴표로 감싸 Postgres에 넣는다.
TEXT_COLS = ["div_date", "cp", "시도", "구시군", "매물그룹", "연월구분",
             "권역구분", "CP변환", "CP변환2"]
NUM_COLS = [
    "지역구분", "cp구분", "매물수", "회원수",
    "현장확인매물수", "현장확인회원수", "홍보확인서매물수", "홍보확인서회원수",
    "홍보확인서2매물수", "홍보확인서2회원수", "전화확인매물수", "전화확인회원수",
    "신홍보확인서매물수", "신홍보확인서회원수", "모바일매물수", "모바일회원수",
    "모바일v2매물수", "모바일v2회원수", "사전매물매물수", "사전매물회원수",
    "현장확인v2매물수", "현장확인v2회원수", "수집회차",
    "구홍보전화매물", "구홍보전화회원", "모바일12매물", "모바일12회원",
    "집주인프로모션매물",
]
# 엑셀에 실제로 나오는 순서(읽어들인 DataFrame의 컬럼 순서와 맞춘다)
COLUMNS = [
    "div_date", "cp", "지역구분", "시도", "구시군", "cp구분", "매물그룹",
    "매물수", "회원수",
    "현장확인매물수", "현장확인회원수", "홍보확인서매물수", "홍보확인서회원수",
    "홍보확인서2매물수", "홍보확인서2회원수", "전화확인매물수", "전화확인회원수",
    "신홍보확인서매물수", "신홍보확인서회원수", "모바일매물수", "모바일회원수",
    "모바일v2매물수", "모바일v2회원수", "사전매물매물수", "사전매물회원수",
    "현장확인v2매물수", "현장확인v2회원수",
    "연월구분", "수집회차", "권역구분", "CP변환", "CP변환2",
    "구홍보전화매물", "구홍보전화회원", "모바일12매물", "모바일12회원",
    "집주인프로모션매물",
]
assert set(COLUMNS) == set(TEXT_COLS) | set(NUM_COLS), "컬럼 분류 누락"

_QUOTED = ", ".join(f'"{c}"' for c in COLUMNS)
_DDL = (
    f"CREATE TABLE IF NOT EXISTS {TABLE} (\n  "
    + ",\n  ".join(f'"{c}" ' + ("TEXT" if c in TEXT_COLS else "DOUBLE PRECISION")
                   for c in COLUMNS)
    + ',\n  "_uploaded_at" TIMESTAMPTZ NOT NULL DEFAULT now()\n);\n'
    f'CREATE INDEX IF NOT EXISTS {TABLE}_month_idx ON {TABLE} ("연월구분");'
)

_ready = False


def _ensure():
    """테이블이 없으면 만든다. db.get_conn()이 공용 SCHEMA를 이미 돌리므로 여기선 CP 것만."""
    global _ready
    conn = db.get_conn()
    if not _ready:
        conn.executescript(_DDL)
        _ready = True
    return conn


def read_excel(path_or_buf) -> pd.DataFrame:
    """업로드된 파일/경로에서 rawdata 시트를 읽는다. 컬럼이 다르면 여기서 막는다."""
    df = pd.read_excel(path_or_buf, sheet_name="rawdata", engine="openpyxl")
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("엑셀에 없는 컬럼: " + ", ".join(missing))
    return df[COLUMNS]


def months_in(df: pd.DataFrame) -> list:
    return sorted(df["연월구분"].astype(str).unique())


def replace_months(df: pd.DataFrame) -> dict:
    """파일에 들어 있는 연월구분만 지우고 다시 넣는다.

    전체 누적본을 주든 새 달치만 주든 똑같이 동작하고, 같은 파일을 두 번 올려도
    행이 불어나지 않는다(그게 이 방식을 쓰는 이유다).
    """
    df = df[COLUMNS].copy()
    for c in TEXT_COLS:
        df[c] = df[c].astype(str)
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    months = months_in(df)

    rows = [tuple(None if pd.isna(v) else v for v in r)
            for r in df.itertuples(index=False, name=None)]
    conn = _ensure()
    try:
        before = conn.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]
        conn.execute(f'DELETE FROM {TABLE} WHERE "연월구분" = ANY(?)', (months,))
        conn.execute_values(
            f"INSERT INTO {TABLE} ({_QUOTED}) VALUES %s", rows, page_size=2000)
        after = conn.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]
    finally:
        conn.close()
    return {"months": months, "inserted": len(rows), "before": before, "after": after}


def version() -> str | None:
    """캐시 키. 행 수와 마지막 적재 시각이 같으면 같은 데이터로 본다.
    테이블이 비어 있으면 None(= 아직 원본 없음)."""
    conn = _ensure()
    try:
        n, ts = conn.execute(
            f'SELECT count(*), max("_uploaded_at") FROM {TABLE}').fetchone()
    finally:
        conn.close()
    return None if not n else f"{n}:{ts}"


def read_all() -> pd.DataFrame:
    conn = _ensure()
    try:
        cur = conn.execute(f"SELECT {_QUOTED} FROM {TABLE}")
        rows = cur.fetchall()
    finally:
        conn.close()
    return pd.DataFrame([tuple(r) for r in rows], columns=COLUMNS)


def summary() -> pd.DataFrame:
    """관리자 화면에 보여줄 '지금 들어 있는 것' — 월별 행 수와 적재 시각."""
    conn = _ensure()
    try:
        rows = conn.execute(
            f'SELECT "연월구분", count(*) AS n, max("_uploaded_at") AS ts '
            f'FROM {TABLE} GROUP BY "연월구분" ORDER BY "연월구분"').fetchall()
    finally:
        conn.close()
    return pd.DataFrame([(r[0], r[1], r[2]) for r in rows],
                        columns=["연월구분", "행 수", "적재 시각"])
