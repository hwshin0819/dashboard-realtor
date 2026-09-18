# -*- coding: utf-8 -*-
"""
7월 스냅샷(realtor-dashboard/snapshots/2026-07.csv)에서 시/도별 '전체 등록'(휴업·정지 포함 전체 개업공인중개사) 숫자를
집계해서 agent_quarterly_stats(month='2026-07')에 채워 넣는다.
(8월/9월은 이미 같은 방식으로 채워져 있었는데 7월만 비어 있었다.)
"""
import csv
import sys
from collections import defaultdict

import db
import region_utils as ru

JULY_CSV = r"C:\Users\proptier\OneDrive - 프롭티어\바탕 화면\realtor-dashboard\snapshots\2026-07.csv"
MONTH = "2026-07"


def main():
    counts = defaultdict(int)
    with open(JULY_CSV, encoding="cp949", errors="replace") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            if len(row) < 2:
                continue
            ld_code_nm = (row[1] or "").strip()
            if not ld_code_nm:
                continue
            sido_full = ru.normalize_sido(ld_code_nm)
            sido_short = ru.SHORT_NAME.get(sido_full)
            if sido_short:
                counts[sido_short] += 1

    total = sum(counts.values())

    conn = db.get_conn()
    for region, count in counts.items():
        conn.execute(
            "INSERT OR REPLACE INTO agent_quarterly_stats (month, region, count) VALUES (?,?,?)",
            (MONTH, region, count),
        )
    conn.execute(
        "INSERT OR REPLACE INTO agent_quarterly_stats (month, region, count) VALUES (?,?,?)",
        (MONTH, "전국", total),
    )
    conn.commit()
    conn.close()

    print(f"{MONTH} 전체 등록 {total}건 (지역 {len(counts)}개) 기록 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
