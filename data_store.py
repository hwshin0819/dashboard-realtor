# -*- coding: utf-8 -*-
"""
로컬 JSON 파일 기반의 간단한 데이터 저장소.
지금 단계는 '틀(UI) + 목업 데이터' 구현이라, 실제 DB 대신 JSON 파일을 사용합니다.
나중에 실제 데이터 수집 로직을 붙일 때 이 파일의 함수들만 실제 로직으로 교체하면 됩니다.
"""
import json
import os
import random
from datetime import datetime, timedelta

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

WEBHOOKS_FILE = os.path.join(DATA_DIR, "webhooks.json")
TARGETS_FILE = os.path.join(DATA_DIR, "targets.json")
SCHEDULE_FILE = os.path.join(DATA_DIR, "schedule.json")
STATS_FILE = os.path.join(DATA_DIR, "mock_stats.json")


# ---------- 공통 JSON 유틸 ----------
def _load_json(path, default):
    if not os.path.exists(path):
        _save_json(path, default)
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def _save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------- 사용자 (로그인 계정) ----------
# Streamlit Cloud는 재배포/재시작마다 파일시스템이 초기화되므로, 로컬 JSON 대신 DB(app_users)에 둔다.
def load_users():
    conn = db.get_conn()
    rows = conn.execute("SELECT username, data FROM app_users").fetchall()
    conn.close()
    return {r["username"]: json.loads(r["data"]) for r in rows}


def save_users(users: dict):
    conn = db.get_conn()
    conn.execute("DELETE FROM app_users")
    if users:
        conn.execute_values(
            "INSERT INTO app_users (username, data) VALUES %s",
            [(username, json.dumps(u, ensure_ascii=False)) for username, u in users.items()],
        )
    conn.close()


# ---------- 웹훅 ----------
DEFAULT_WEBHOOKS = [
    {"이름": "폐업 알림", "URL": "https://hooks.example.com/closed", "이벤트": "폐업 발생 시", "사용": True},
    {"이름": "신규 개업 알림", "URL": "https://hooks.example.com/opened", "이벤트": "신규 개업 시", "사용": True},
    {"이름": "수집 실패 알림", "URL": "https://hooks.example.com/error", "이벤트": "수집 실패 시", "사용": False},
]


def load_webhooks():
    return _load_json(WEBHOOKS_FILE, DEFAULT_WEBHOOKS)


def save_webhooks(rows):
    _save_json(WEBHOOKS_FILE, rows)


# ---------- 수집 대상 ----------
DEFAULT_TARGETS = [
    {"시도": "서울특별시", "시군구": "강남구", "데이터 소스": "브이월드 중개업 정보", "사용": True},
    {"시도": "서울특별시", "시군구": "서초구", "데이터 소스": "브이월드 중개업 정보", "사용": True},
    {"시도": "서울특별시", "시군구": "송파구", "데이터 소스": "브이월드 중개업 정보", "사용": True},
    {"시도": "서울특별시", "시군구": "마포구", "데이터 소스": "브이월드 중개업 정보", "사용": True},
    {"시도": "서울특별시", "시군구": "영등포구", "데이터 소스": "브이월드 중개업 정보", "사용": False},
]


def load_targets():
    return _load_json(TARGETS_FILE, DEFAULT_TARGETS)


def save_targets(rows):
    _save_json(TARGETS_FILE, rows)


# ---------- 배치 스케줄 ----------
DEFAULT_SCHEDULE = [
    {"작업명": "일별 수집", "주기": "매일", "실행시각": "02:00", "사용": True},
    {"작업명": "월별 통계 집계", "주기": "매월", "실행시각": "03:00", "사용": True},
    {"작업명": "웹훅 재발송", "주기": "매주", "실행시각": "09:00", "사용": False},
]


def load_schedule():
    return _load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)


def save_schedule(rows):
    _save_json(SCHEDULE_FILE, rows)


# ---------- 접속 로그 ----------
# 위와 같은 이유(Streamlit Cloud 파일시스템 초기화)로 로컬 JSONL 대신 DB(access_log)에 쌓는다.
def append_access_log(user_id: str, action: str, success: bool, note: str = "", ip: str | None = None):
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO access_log (ts, user_id, action, result, note, ip) VALUES (?,?,?,?,?,?)",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id, action,
            "성공" if success else "실패", note, ip or "-",
        ),
    )
    conn.close()


def load_access_log():
    conn = db.get_conn()
    rows = conn.execute("SELECT ts, user_id, action, result, note, ip FROM access_log ORDER BY id").fetchall()
    conn.close()
    return [
        {"시각": r["ts"], "아이디": r["user_id"], "동작": r["action"], "결과": r["result"], "비고": r["note"], "IP": r["ip"]}
        for r in rows
    ]


# ---------- 개요용 목업 통계 ----------
REGIONS = ["강남구", "서초구", "송파구", "마포구", "영등포구"]


def _generate_mock_stats():
    random.seed(42)
    months = []
    today = datetime.now().replace(day=1)
    for i in range(11, -1, -1):
        m = (today.month - i - 1) % 12 + 1
        y = today.year + ((today.month - i - 1) // 12)
        months.append(f"{y}-{m:02d}")

    rows = []
    running_active = {r: random.randint(80, 150) for r in REGIONS}
    for month in months:
        for region in REGIONS:
            opened = random.randint(3, 18)
            closed = random.randint(2, 14)
            running_active[region] = max(0, running_active[region] + opened - closed)
            rows.append(
                {
                    "월": month,
                    "지역": region,
                    "개업": opened,
                    "폐업": closed,
                    "영업중": running_active[region],
                }
            )
    return rows


def load_mock_stats():
    return _load_json(STATS_FILE, _generate_mock_stats())
