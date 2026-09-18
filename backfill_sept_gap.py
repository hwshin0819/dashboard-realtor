# -*- coding: utf-8 -*-
"""
9/1(사용자 제공 스냅샷) ~ 9/11(우리 자체 부트스트랩) 사이 공백을 메운다.
두 스냅샷을 diff해서 그 사이의 개업/폐업을 추정하고, event_date='2026-09-01'로 기록한다.
(정확한 일자는 알 수 없어 9월 집계에는 포함되도록 월초로 귀속시킨다)
"""
import sys
from collections import defaultdict

import openpyxl

import db
import excel_export

SNAPSHOT_FILE = "aug_snapshot2.xlsx"
GAP_DATE = "2026-09-01"


def load_snapshot(path):
    """
    등록번호(jurirno) 셀이 엑셀에서 숫자 타입으로 저장된 행들이 있다(예: 29, 43, 46처럼).
    문자열로 통일해서 키를 만들지 않으면 29(int) != "29"(str) 로 취급되어
    같은 사무소가 개업+폐업으로 이중 집계되는 버그가 생긴다. 지역명도 트레일링 공백이 섞여있어 같이 정리한다.
    """
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["Sheet1"]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        _, ld_code_nm, jurirno, bsnm, _, status_code, *_ = row
        if jurirno is None or jurirno == "":
            continue
        key = str(jurirno).strip()
        out[key] = {
            "ld_code_nm": (ld_code_nm or "").strip(),
            "status_code": str(status_code),
            "bsnm": bsnm,
        }
    return out


def main():
    conn = db.get_conn()
    already = conn.execute("SELECT COUNT(*) FROM events WHERE event_date=?", (GAP_DATE,)).fetchone()[0]
    if already:
        conn.close()
        raise SystemExit(f"[안내] {GAP_DATE} 로 이미 {already}건이 기록되어 있습니다. 중복 실행을 막기 위해 종료합니다.")

    snapshot = load_snapshot(SNAPSHOT_FILE)

    current = {
        str(r["jurirno"]).strip(): r
        for r in conn.execute(
            "SELECT jurirno, ld_code, ld_code_nm, bsnm_cmpnm, sttus_se_code FROM offices WHERE closed_date IS NULL"
        ).fetchall()
    }

    opened_ids = set(current) - set(snapshot)
    closed_ids = set(snapshot) - set(current)

    opened_by_region = defaultdict(int)
    closed_by_region = defaultdict(int)

    for jurirno in opened_ids:
        r = current[jurirno]
        conn.execute(
            """INSERT INTO events (event_date, jurirno, event_type, from_status, to_status, ld_code, ld_code_nm, bsnm_cmpnm)
               VALUES (?,?,?,?,?,?,?,?)""",
            (GAP_DATE, jurirno, "open", None, r["sttus_se_code"], r["ld_code"], r["ld_code_nm"], r["bsnm_cmpnm"]),
        )
        opened_by_region[r["ld_code_nm"]] += 1

    for jurirno in closed_ids:
        s = snapshot[jurirno]
        conn.execute(
            """INSERT INTO events (event_date, jurirno, event_type, from_status, to_status, ld_code, ld_code_nm, bsnm_cmpnm)
               VALUES (?,?,?,?,?,?,?,?)""",
            (GAP_DATE, jurirno, "close", s["status_code"], None, None, s["ld_code_nm"], s["bsnm"]),
        )
        closed_by_region[s["ld_code_nm"]] += 1

    regions = set(opened_by_region) | set(closed_by_region)
    for region in regions:
        conn.execute(
            """INSERT OR REPLACE INTO daily_region_stats (date, region, active, opened, closed)
               VALUES (?,?,0,?,?)""",
            (GAP_DATE, region, opened_by_region.get(region, 0), closed_by_region.get(region, 0)),
        )

    conn.commit()
    conn.close()

    excel_export.rebuild_from_db()

    print(
        f"개업(추정) {len(opened_ids)}건 / 폐업(추정) {len(closed_ids)}건 -> {GAP_DATE} 로 기록, 엑셀 재생성 완료",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
