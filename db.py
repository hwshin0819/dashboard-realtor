# -*- coding: utf-8 -*-
"""중개업소 데이터 저장용 DB. 원래는 로컬 SQLite(data/offices.db)였으나, 랩탑이 꺼져 있어도
접근 가능하도록 Supabase(Postgres)로 옮겼다. 아래 _Conn/_Cursor는 나머지 코드(conn.execute(...),
row["컬럼명"], row[0])를 하나도 안 고치고 그대로 쓸 수 있도록 sqlite3.Connection 인터페이스를
흉내 낸 얇은 래퍼다."""
import os
import re

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ["SUPABASE_DB_URL"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS offices (
    jurirno TEXT PRIMARY KEY,
    ld_code TEXT,
    ld_code_nm TEXT,
    bsnm_cmpnm TEXT,
    brkr_nm TEXT,
    sttus_se_code TEXT,
    sttus_se_code_nm TEXT,
    regist_de TEXT,
    estbs_begin_de TEXT,
    estbs_end_de TEXT,
    last_updt_dt TEXT,
    mnnmadr TEXT,
    rdnmadr TEXT,
    rdnmadr_code TEXT,
    first_seen_date TEXT,
    last_seen_date TEXT,
    closed_date TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_date TEXT NOT NULL,
    jurirno TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    ld_code TEXT,
    ld_code_nm TEXT,
    bsnm_cmpnm TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

CREATE TABLE IF NOT EXISTS daily_region_stats (
    date TEXT NOT NULL,
    region TEXT NOT NULL,
    active INTEGER,
    opened INTEGER,
    closed INTEGER,
    PRIMARY KEY (date, region)
);
CREATE INDEX IF NOT EXISTS idx_daily_region_date ON daily_region_stats(date);

CREATE TABLE IF NOT EXISTS legacy_monthly_stats (
    month TEXT NOT NULL,
    region TEXT NOT NULL,
    opened INTEGER,
    closed INTEGER,
    source TEXT,
    PRIMARY KEY (month, region)
);

CREATE TABLE IF NOT EXISTS agent_quarterly_stats (
    month TEXT NOT NULL,
    region TEXT NOT NULL,
    count INTEGER,
    PRIMARY KEY (month, region)
);

CREATE TABLE IF NOT EXISTS collection_log (
    collected_date TEXT PRIMARY KEY,
    total_active INTEGER,
    total_pause INTEGER,
    total_ext INTEGER,
    total_stop INTEGER,
    collected_at TEXT
);

-- 국토부 실거래가(부동산 거래량 현황 메뉴): 시군구 x 유형 x 거래유형 x 월 단위 집계.
CREATE TABLE IF NOT EXISTS transaction_monthly (
    ym TEXT NOT NULL,
    sigungu_code TEXT NOT NULL,
    property_type TEXT NOT NULL,
    trade_type TEXT NOT NULL,
    count INTEGER,          -- trade_type='전월세'면 전세+월세 합계(하위호환용, 계속 채움)
    avg_price INTEGER,
    avg_deposit INTEGER,    -- trade_type='전월세'면 전세+월세 통합 평균(하위호환용)
    avg_rent INTEGER,       -- 월세 계약의 평균 월세금
    PRIMARY KEY (ym, sigungu_code, property_type, trade_type)
);
-- 전세/월세를 구분해서 보려고 나중에 추가한 컬럼들. 기존 count/avg_deposit는 그대로 두고 옆에 더한다.
ALTER TABLE transaction_monthly ADD COLUMN IF NOT EXISTS count_jeonse INTEGER;
ALTER TABLE transaction_monthly ADD COLUMN IF NOT EXISTS count_wolse INTEGER;
ALTER TABLE transaction_monthly ADD COLUMN IF NOT EXISTS avg_deposit_jeonse INTEGER;
ALTER TABLE transaction_monthly ADD COLUMN IF NOT EXISTS avg_deposit_wolse INTEGER;
-- 전세 중 계약갱신청구권(주택임대차보호법)을 사용한 건수. 국토부 API의 '갱신요구권사용' 필드가
-- "사용"/공백(NaN)으로만 내려와서 신규 전세와 갱신 전세를 구분할 수 있다.
ALTER TABLE transaction_monthly ADD COLUMN IF NOT EXISTS count_jeonse_renewal INTEGER;

-- 재개 가능한 백필 진행 상황 체크포인트: 이 조합을 이미 수집했는지 여부.
CREATE TABLE IF NOT EXISTS transaction_collect_progress (
    sigungu_code TEXT NOT NULL,
    property_type TEXT NOT NULL,
    trade_type TEXT NOT NULL,
    ym TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (sigungu_code, property_type, trade_type, ym)
);

-- 로그인 계정. Streamlit Cloud는 파일시스템이 재배포/재시작 때마다 초기화되므로
-- users.json 같은 로컬 파일로는 계정이 못 살아남는다 — DB에 둬야 한다.
CREATE TABLE IF NOT EXISTS app_users (
    username TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

-- 접속 로그. 위와 같은 이유로 로컬 JSONL 파일 대신 DB에 쌓는다.
CREATE TABLE IF NOT EXISTS access_log (
    id SERIAL PRIMARY KEY,
    ts TEXT,
    user_id TEXT,
    action TEXT,
    result TEXT,
    note TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_access_log_ts ON access_log(ts);
"""

# SQLite "INSERT OR REPLACE INTO tbl (...)"를 Postgres "INSERT ... ON CONFLICT(pk) DO UPDATE"로
# 바꾸는 데 필요한, 테이블별 기본키 정의.
_PK = {
    "daily_region_stats": ["date", "region"],
    "legacy_monthly_stats": ["month", "region"],
    "agent_quarterly_stats": ["month", "region"],
    "collection_log": ["collected_date"],
    "transaction_monthly": ["ym", "sigungu_code", "property_type", "trade_type"],
    "transaction_collect_progress": ["sigungu_code", "property_type", "trade_type", "ym"],
}

_INSERT_OR_REPLACE_HEAD_RE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(", re.IGNORECASE,
)


def _find_matching_paren(s: str, open_idx: int) -> int:
    """s[open_idx]는 '(' 라고 가정하고, 짝이 맞는 ')' 의 인덱스를 찾는다(중첩 괄호 대응)."""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("괄호 짝이 맞지 않습니다: " + s)


def _rewrite_insert_or_replace(query: str) -> str:
    """'INSERT OR REPLACE INTO tbl (...) VALUES (...)' 를
    'INSERT INTO tbl (...) VALUES (...) ON CONFLICT(pk) DO UPDATE SET ...' 로 바꾼다.
    VALUES 안에 to_char(...)처럼 괄호가 중첩된 함수 호출이 올 수 있어 단순 정규식 대신
    괄호 깊이를 세어 짝을 맞춘다."""
    m = _INSERT_OR_REPLACE_HEAD_RE.search(query)
    if not m:
        return query

    table = m.group(1)
    cols_open = m.end() - 1
    cols_close = _find_matching_paren(query, cols_open)
    cols_str = query[cols_open + 1: cols_close]
    cols = [c.strip() for c in cols_str.split(",")]

    values_m = re.search(r"VALUES\s*\(", query[cols_close:], re.IGNORECASE)
    if not values_m:
        raise ValueError("VALUES 절을 찾을 수 없습니다: " + query)
    vals_open = cols_close + values_m.end() - 1
    vals_close = _find_matching_paren(query, vals_open)
    vals_str = query[vals_open + 1: vals_close]

    pk = _PK.get(table.strip())
    if pk is None:
        raise ValueError(f"'{table}' 테이블의 기본키가 db.py의 _PK에 정의되어 있지 않습니다.")
    update_cols = [c for c in cols if c not in pk]
    set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
    upsert = (
        f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str}) "
        f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {set_clause}"
    )
    return query[: m.start()] + upsert + query[vals_close + 1:]


def _translate(query: str) -> str:
    """SQLite 전용 문법을 Postgres 문법으로 바꾼다: datetime('now','localtime') → 서울 시각,
    INSERT OR REPLACE → ON CONFLICT DO UPDATE, '?' 플레이스홀더 → '%s'."""
    query = re.sub(
        r"datetime\(\s*'now'\s*,\s*'localtime'\s*\)",
        "to_char(now() AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')",
        query,
        flags=re.IGNORECASE,
    )
    query = _rewrite_insert_or_replace(query)
    return query.replace("?", "%s")


class _Row:
    """psycopg2가 돌려주는 튜플을, sqlite3.Row처럼 row["컬럼명"]과 row[0] 둘 다 되게 감싼다."""

    __slots__ = ("_values", "_cols")

    def __init__(self, values, cols):
        self._values = values
        self._cols = cols

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._cols.index(key)]
        return self._values[key]

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self):
        return repr(dict(zip(self._cols, self._values)))


class _Cursor:
    def __init__(self, cur):
        self._cur = cur
        self._cols = [d[0] for d in cur.description] if cur.description else []

    def fetchall(self):
        return [_Row(row, self._cols) for row in self._cur.fetchall()]

    def fetchone(self):
        row = self._cur.fetchone()
        return _Row(row, self._cols) if row is not None else None

    def __iter__(self):
        return (_Row(row, self._cols) for row in self._cur)

    @property
    def rowcount(self):
        return self._cur.rowcount


class _Conn:
    """psycopg2 커넥션을 sqlite3.Connection과 같은 인터페이스(conn.execute(...))로 감싼다.
    close()는 실제로 끊지 않고 풀에 반납한다 — 호출하는 쪽 코드(매 함수마다 get_conn()...close())는
    그대로 두고, 커넥션 자체만 재사용해 매번 새로 맺던 TCP+TLS 핸드셰이크 비용을 없앤다."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def _reconnect(self):
        """풀에 오래 놀고 있던 커넥션을 Supabase 쪽에서 먼저 끊어버린 경우 대비.
        죽은 커넥션은 풀에 돌려주지 않고 진짜로 버린 뒤 새로 하나 받아온다."""
        try:
            _pool.putconn(self._conn, close=True)
        except Exception:
            pass
        self._conn = _pool.getconn()

    def _run(self, fn):
        """fn(conn)을 실행하고, 커넥션이 죽어 있었으면(Supabase 쪽 idle timeout 등) 한 번만
        재연결 후 재시도한다."""
        try:
            return fn(self._conn)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            self._reconnect()
            return fn(self._conn)

    def execute(self, query: str, params=()) -> _Cursor:
        q = _translate(query)

        def _do(conn):
            cur = conn.cursor()
            cur.execute(q, params)
            conn.commit()
            return cur

        return _Cursor(self._run(_do))

    def executescript(self, script: str):
        def _do(conn):
            cur = conn.cursor()
            cur.execute(script)
            conn.commit()

        self._run(_do)

    def execute_values(self, query: str, values: list, template: str = None, page_size: int = 1000):
        """대량 INSERT/UPDATE 전용. 건마다 conn.execute()를 부르면 네트워크 DB에서는
        건수만큼 왕복 지연이 그대로 곱해진다(수만 건이면 수십 분). psycopg2.extras.execute_values로
        한 번에 묶어 보낸다. query는 'INSERT INTO t (...) VALUES %s ...' 형태."""
        if not values:
            return 0

        def _do(conn):
            cur = conn.cursor()
            psycopg2.extras.execute_values(cur, query, values, template=template, page_size=page_size)
            conn.commit()
            return cur.rowcount

        return self._run(_do)

    def commit(self):
        self._conn.commit()

    def close(self):
        _pool.putconn(self._conn)


# 매번 새 커넥션을 맺지 않고 풀에서 빌려 쓴다 — 페이지 하나 열 때 get_conn()이 5~6번씩
# 불리는데, 그때마다 네트워크 너머 Supabase와 새로 TCP+TLS 핸드셰이크를 하면 그 지연이
# 그대로 곱해져 체감 속도가 느려진다. minconn=1, maxconn=10은 이 앱 동시 사용자 규모
# (사내 몇 명 + 소수 공개 접속) 대비 여유 있는 값이다.
_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DB_URL)
_schema_ready = False


def get_conn() -> _Conn:
    global _schema_ready
    pg_conn = _pool.getconn()
    conn = _Conn(pg_conn)
    if not _schema_ready:
        conn.executescript(SCHEMA)
        _schema_ready = True
    return conn
