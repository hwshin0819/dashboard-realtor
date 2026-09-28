# -*- coding: utf-8 -*-
"""로그인 계정과 접속 로그를 담는 저장소. 둘 다 Streamlit Cloud가 재배포/재시작마다
파일시스템을 초기화하므로 로컬 파일이 아니라 DB(app_users/access_log)에 둔다."""
import json
from datetime import datetime

import db


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
