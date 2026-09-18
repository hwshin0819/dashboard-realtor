# -*- coding: utf-8 -*-
"""수집 대상 탭."""
import pandas as pd
import streamlit as st

import data_store as ds


def render():
    st.subheader("수집 대상")
    st.caption("브이월드 디지털트윈 국토에서 어떤 지역의 중개업 정보를 수집할지 설정합니다.")

    rows = ds.load_targets()
    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "데이터 소스": st.column_config.SelectboxColumn(
                options=["브이월드 중개업 정보", "브이월드 필지 정보"]
            ),
            "사용": st.column_config.CheckboxColumn(),
        },
        key="target_editor",
    )

    if st.button("저장", type="primary", key="save_targets", use_container_width=True):
        ds.save_targets(edited.to_dict(orient="records"))
        st.success("수집 대상 설정을 저장했습니다.")

    st.caption(f"현재 사용 중인 수집 대상: {int(edited['사용'].sum()) if len(edited) else 0}건")
