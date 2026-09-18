# -*- coding: utf-8 -*-
"""
개업공인중개사 현황(분기별) 자료를 agent_quarterly_stats 에 채워 넣는다.
분기 표기: 2020/01=1분기(3월말), 02=2분기(6월말), 03=3분기(9월말), 04=4분기(12월말)
"""
import csv
import sys

import db

RAW_FILE = "agent_quarterly_raw.tsv"
QUARTER_TO_MONTH = {"01": "03", "02": "06", "03": "09", "04": "12"}


def quarter_to_month_end(q: str) -> str:
    year, q_no = q.split("/")
    return f"{year}-{QUARTER_TO_MONTH[q_no]}"


def main():
    conn = db.get_conn()
    inserted = 0
    with open(RAW_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            month = quarter_to_month_end(row["분기"].strip())
            region_raw = row["구분"].strip()
            region = "전국" if region_raw == "계" else region_raw
            count = int(row["계"].replace(",", "").strip())
            conn.execute(
                "INSERT OR REPLACE INTO agent_quarterly_stats (month, region, count) VALUES (?,?,?)",
                (month, region, count),
            )
            inserted += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM agent_quarterly_stats").fetchone()[0]
    conn.close()
    print(f"삽입/갱신 {inserted}행, 테이블 총 {total}행", file=sys.stderr)


if __name__ == "__main__":
    main()
