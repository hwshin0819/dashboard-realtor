# -*- coding: utf-8 -*-
"""8/31 시점 '영업중' 실측 스냅샷을 daily_region_stats에 기록한다 (개업/폐업은 별도 스크립트에서 이미 처리됨)."""
import sys
from collections import defaultdict

import openpyxl

import db
import excel_export

SNAPSHOT_FILE = "aug_snapshot2.xlsx"
SNAPSHOT_DATE = "2026-08-31"


def main():
    conn = db.get_conn()
    already = conn.execute("SELECT COUNT(*) FROM daily_region_stats WHERE date=?", (SNAPSHOT_DATE,)).fetchone()[0]
    if already:
        conn.close()
        raise SystemExit(f"[안내] {SNAPSHOT_DATE} 는 이미 기록되어 있습니다.")

    wb = openpyxl.load_workbook(SNAPSHOT_FILE, read_only=True)
    ws = wb["Sheet1"]
    active_by_region = defaultdict(int)
    for row in ws.iter_rows(min_row=2, values_only=True):
        ld_code_nm, status_name = row[1], row[6]
        if status_name == "영업중":
            active_by_region[ld_code_nm] += 1

    for region, count in active_by_region.items():
        conn.execute(
            """INSERT OR REPLACE INTO daily_region_stats (date, region, active, opened, closed)
               VALUES (?,?,?,0,0)""",
            (SNAPSHOT_DATE, region, count),
        )
    conn.commit()
    conn.close()

    excel_export.rebuild_from_db()
    print(f"{SNAPSHOT_DATE} 영업중 스냅샷 {sum(active_by_region.values())}건 기록 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
