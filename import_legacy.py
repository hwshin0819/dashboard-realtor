# -*- coding: utf-8 -*-
"""
realtor(github pages) 저장소의 과거 이력(data.json)을 한 번만 가져와 legacy_monthly_stats에 채워 넣는다.
2026-09부터는 우리 자체 브이월드 수집이 데이터를 갖고 있으므로, 그 이전 달까지만 가져온다.
"""
import json
import sys

import db

LEGACY_FILE = "data/realtor_legacy_data.json"
CUTOFF_MONTH = "2026-09"  # 이 달부터는 자체 수집 데이터를 쓰므로 legacy에서 제외


def main():
    with open(LEGACY_FILE, encoding="utf-8") as f:
        data = json.load(f)

    months = data["months"]
    conn = db.get_conn()
    inserted = 0

    for region, series in data["regions"].items():
        opens = series.get("open", [])
        closes = series.get("close", [])
        for i, month in enumerate(months):
            if month >= CUTOFF_MONTH:
                continue
            o = opens[i] if i < len(opens) else None
            c = closes[i] if i < len(closes) else None
            if o is None and c is None:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO legacy_monthly_stats (month, region, opened, closed, source)
                   VALUES (?,?,?,?,?)""",
                (month, region, o, c, "realtor_backfill"),
            )
            inserted += 1

    conn.commit()
    row_count = conn.execute("SELECT COUNT(*) FROM legacy_monthly_stats").fetchone()[0]
    conn.close()
    print(f"삽입/갱신 {inserted}행, 테이블 총 {row_count}행", file=sys.stderr)


if __name__ == "__main__":
    main()
