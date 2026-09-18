# -*- coding: utf-8 -*-
"""vworld_client 동작 확인용 테스트. 종로구(11110) 데이터를 조금만 받아봅니다."""
import json
from collections import Counter

import vworld_client as vc

if __name__ == "__main__":
    rows = vc.fetch_all(ld_code="11110")
    status_counts = Counter(r.get("sttusSeCodeNm") for r in rows)

    result = {
        "총건수": len(rows),
        "상태별_건수": dict(status_counts),
        "샘플_3건": rows[:3],
    }
    with open("test_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("test_result.json 에 저장 완료, 건수:", len(rows))
