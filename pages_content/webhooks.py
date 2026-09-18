# -*- coding: utf-8 -*-
"""웹훅 관리 탭."""
import pandas as pd
import streamlit as st

import data_store as ds


def render():
    st.subheader("웹훅 관리")
    st.caption("개업/폐업 등 이벤트가 발생했을 때 알림을 보낼 웹훅 URL을 등록·관리합니다.")

    rows = ds.load_webhooks()
    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "이벤트": st.column_config.SelectboxColumn(
                options=["신규 개업 시", "폐업 발생 시", "수집 실패 시", "상태 변경 시"]
            ),
            "사용": st.column_config.CheckboxColumn(),
            "URL": st.column_config.TextColumn(width="large"),
        },
        key="webhook_editor",
    )

    if st.button("저장", type="primary", key="save_webhooks", use_container_width=True):
        ds.save_webhooks(edited.to_dict(orient="records"))
        st.success("웹훅 설정을 저장했습니다.")

    st.caption("표에서 마지막 빈 줄에 값을 입력하면 새 웹훅이 추가되고, 행을 선택 후 삭제 아이콘으로 제거할 수 있습니다.")
