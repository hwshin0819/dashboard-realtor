# -*- coding: utf-8 -*-
"""수집 테스트 탭: 실제 수집 로직이 붙기 전, 동작 흐름을 미리 확인하는 목업 테스트."""
import random
import time
from datetime import datetime

import pandas as pd
import streamlit as st

import data_store as ds


def _fake_run(target_label: str):
    time.sleep(1.0)
    new_count = random.randint(0, 8)
    changed_count = random.randint(0, 5)
    closed_count = random.randint(0, 4)
    elapsed = round(random.uniform(0.8, 3.5), 1)

    sample_rows = []
    names = ["행복공인중개사사무소", "미래부동산중개", "한빛공인중개사사무소", "새들녘부동산", "중앙공인중개사"]
    statuses = ["영업중", "개업", "폐업"]
    for i in range(min(5, new_count + changed_count + 1)):
        sample_rows.append(
            {
                "사무소명": random.choice(names),
                "상태": random.choice(statuses),
                "소재지": target_label,
                "확인시각": datetime.now().strftime("%H:%M:%S"),
            }
        )

    return {
        "신규": new_count,
        "변경감지": changed_count,
        "폐업감지": closed_count,
        "소요시간": elapsed,
        "샘플": sample_rows,
    }


def render():
    st.subheader("수집 테스트")
    st.caption("실제 브이월드 API 연동 전, 수집이 정상적으로 동작하는지 미리 확인하는 화면입니다. (현재는 결과가 무작위로 생성되는 목업입니다)")

    targets = ds.load_targets()
    enabled = [t for t in targets if t.get("사용")]

    if not enabled:
        st.warning("사용 중인 수집 대상이 없습니다. 먼저 '수집 대상' 탭에서 대상을 추가/활성화해주세요.")
        return

    options = [f"{t['시도']} {t['시군구']}" for t in enabled]
    choice = st.selectbox("테스트할 수집 대상", options)

    if st.button("테스트 실행", type="primary", use_container_width=True):
        with st.spinner(f"'{choice}' 대상으로 수집 테스트를 실행하는 중..."):
            result = _fake_run(choice)

        st.success(
            f"테스트 완료 — 신규 {result['신규']}건 / 변경 {result['변경감지']}건 / "
            f"폐업 감지 {result['폐업감지']}건 (소요 {result['소요시간']}초)"
        )
        if result["샘플"]:
            st.markdown("**샘플 결과 미리보기**")
            st.dataframe(pd.DataFrame(result["샘플"]), use_container_width=True, hide_index=True)
