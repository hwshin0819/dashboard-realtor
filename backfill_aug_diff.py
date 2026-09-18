# -*- coding: utf-8 -*-
"""
7월 스냅샷(realtor-dashboard/snapshots/2026-07.csv)과 8월 스냅샷(2026-08.xlsx)을 비교(diff)해서
8월의 시군구별 개업/폐업을 실제로 계산해 daily_region_stats(2026-08-31)에 채워 넣는다.
(기존에는 8월 스냅샷 하나만 있어서 영업중 숫자만 기록되고 개업/폐업은 0으로 남아 있었다.)
"""
import csv
import sys
from collections import defaultdict

import openpyxl

import db
import excel_export

JULY_CSV = r"C:\Users\proptier\OneDrive - 프롭티어\바탕 화면\realtor-dashboard\snapshots\2026-07.csv"
AUG_XLSX = r"C:\Users\proptier\OneDrive - 프롭티어\바탕 화면\realtor-dashboard\snapshots\2026-08.xlsx"
AUG_DATE = "2026-08-31"


def load_csv_snapshot(path: str) -> dict:
    out = {}
    with open(path, encoding="cp949", errors="replace") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            if len(row) < 7:
                continue
            ld_code_nm, regno, status_name = row[1], row[2], row[6]
            if not regno:
                continue
            out[str(regno).strip()] = {"ld_code_nm": (ld_code_nm or "").strip(), "status_name": status_name}
    return out


def load_xlsx_snapshot(path: str) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["Sheet1"]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        ld_code_nm, regno, status_name = row[1], row[2], row[6]
        if not regno:
            continue
        out[str(regno).strip()] = {"ld_code_nm": (ld_code_nm or "").strip(), "status_name": status_name}
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
    for regno in opened_ids:
        opened[cur[regno]["ld_code_nm"]] += 1
    for regno in closed_ids:
        closed[prev[regno]["ld_code_nm"]] += 1
    return opened, closed


def main():
    july = load_csv_snapshot(JULY_CSV)
    aug = load_xlsx_snapshot(AUG_XLSX)

    active_aug = active_by_region(aug)
    opened_aug, closed_aug = diff_by_region(july, aug)

    conn = db.get_conn()
    regions = set(active_aug) | set(opened_aug) | set(closed_aug)
    for region in regions:
        conn.execute(
            "INSERT OR REPLACE INTO daily_region_stats (date, region, active, opened, closed) VALUES (?,?,?,?,?)",
            (AUG_DATE, region, active_aug.get(region, 0), opened_aug.get(region, 0), closed_aug.get(region, 0)),
        )
    conn.commit()
    conn.close()

    excel_export.rebuild_from_db()

    print(
        f"7월 {len(july)}건 vs 8월 {len(aug)}건 비교 완료. "
        f"8월 개업(추정) {sum(opened_aug.values())}건 / 폐업(추정) {sum(closed_aug.values())}건, "
        f"영업중 {sum(active_aug.values())}건 기록 완료",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
