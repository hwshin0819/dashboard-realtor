# -*- coding: utf-8 -*-
"""
0607.xlsx (시트: 202606, 202607) 을 이용해
- 2026-06-30 : 시군구별 영업중 스냅샷 (첫 스냅샷이라 개업/폐업은 0)
- 2026-07-31 : 시군구별 영업중 스냅샷 + 6월 대비 개업/폐업(diff)
을 daily_region_stats 에 채워 넣는다.
"""
import sys
from collections import defaultdict

import openpyxl

import db

SNAPSHOT_FILE = "june_july.xlsx"
JUNE_DATE = "2026-06-30"
JULY_DATE = "2026-07-31"


def load_snapshot(sheet_name: str) -> dict:
    wb = openpyxl.load_workbook(SNAPSHOT_FILE, read_only=True)
    ws = wb[sheet_name]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        _, ld_code_nm, jurirno, bsnm, _, status_code, status_name, *_ = row
        if jurirno is None or jurirno == "":
            continue
        key = str(jurirno).strip()
        out[key] = {
            "ld_code_nm": (ld_code_nm or "").strip(),
            "status_name": status_name,
        }
    return out


def active_by_region(snapshot: dict) -> dict:
    counts = defaultdict(int)
    for info in snapshot.values():
        if info["status_name"] == "영업중":
            counts[info["ld_code_nm"]] += 1
    return counts


def diff_by_region(prev: dict, cur: dict) -> tuple[dict, dict]:
    opened_ids = set(cur) - set(prev)
    closed_ids = set(prev) - set(cur)
    opened = defaultdict(int)
    closed = defaultdict(int)
    for jid in opened_ids:
        opened[cur[jid]["ld_code_nm"]] += 1
    for jid in closed_ids:
        closed[prev[jid]["ld_code_nm"]] += 1
    return opened, closed


def main():
    conn = db.get_conn()
    already = conn.execute(
        "SELECT COUNT(*) FROM daily_region_stats WHERE date IN (?,?)", (JUNE_DATE, JULY_DATE)
    ).fetchone()[0]
    if already:
        conn.close()
        raise SystemExit(f"[안내] {JUNE_DATE}/{JULY_DATE} 데이터가 이미 있습니다. 중복 실행 방지를 위해 종료합니다.")

    snap_06 = load_snapshot("202606")
    snap_07 = load_snapshot("202607")

    active_06 = active_by_region(snap_06)
    active_07 = active_by_region(snap_07)
    opened_07, closed_07 = diff_by_region(snap_06, snap_07)

    regions_06 = set(active_06)
    for region in regions_06:
        conn.execute(
            "INSERT OR REPLACE INTO daily_region_stats (date, region, active, opened, closed) VALUES (?,?,?,0,0)",
            (JUNE_DATE, region, active_06[region]),
        )

    regions_07 = set(active_07) | set(opened_07) | set(closed_07)
    for region in regions_07:
        conn.execute(
            "INSERT OR REPLACE INTO daily_region_stats (date, region, active, opened, closed) VALUES (?,?,?,?,?)",
            (JULY_DATE, region, active_07.get(region, 0), opened_07.get(region, 0), closed_07.get(region, 0)),
        )

    conn.commit()
    conn.close()

    print(
        f"6월 스냅샷 {sum(active_06.values())}건, 7월 스냅샷 {sum(active_07.values())}건, "
        f"7월 개업(추정) {sum(opened_07.values())}건 / 폐업(추정) {sum(closed_07.values())}건 기록 완료",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
