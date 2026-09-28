# -*- coding: utf-8 -*-
"""배치 스케줄 탭."""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import data_store as ds


def _next_run(freq: str, hhmm: str) -> str:
    """
    다음 실행 예정 시각을 계산합니다. (참고용 표시 - 실제 실행기는 아직 없습니다)
    요일을 별도로 지정하는 항목이 없으므로, '매주'는 '오늘/이 시각 기준으로 7일마다'로 계산합니다.
    """
    try:
        hour, minute = map(int, hhmm.split(":"))
    except Exception:
        return "-"

    now = datetime.now()

    if freq == "매일":
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
    elif freq == "매주":
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=7)
    elif freq == "매월":
        # 매월 1일 지정 시각에 실행한다고 가정
        candidate = now.replace(day=1, hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            # 다음 달 1일로 이동 (월말 일수 차이에 안전한 방식)
            candidate = (candidate.replace(day=28) + timedelta(days=4)).replace(
                day=1, hour=hour, minute=minute, second=0, microsecond=0
            )
    else:
        return "-"

    return candidate.strftime("%Y-%m-%d %H:%M")


def render():
    st.subheader("배치 스케줄")
    st.caption("수집·통계 작업을 언제, 얼마나 자주 실행할지 설정합니다. (현재 단계에서는 실제 실행기는 붙어있지 않고, 설정만 저장됩니다)")

    rows = ds.load_schedule()
    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "주기": st.column_config.SelectboxColumn(options=["매일", "매주", "매월"]),
            "사용": st.column_config.CheckboxColumn(),
        },
        key="schedule_editor",
    )

    if st.button("저장", type="primary", key="save_schedule", use_container_width=True):
        ds.save_schedule(edited.to_dict(orient="records"))
        st.success("배치 스케줄을 저장했습니다.")

    st.divider()
    st.markdown("**다음 실행 예정 (참고용, 자동 계산)**")
    if len(edited):
        preview = edited.copy()
        preview["다음 실행 예정"] = preview.apply(
            lambda r: _next_run(r.get("주기", ""), r.get("실행시각", "")) if r.get("사용") else "사용 안 함",
            axis=1,
        )
        st.dataframe(
            preview[["작업명", "주기", "실행시각", "사용", "다음 실행 예정"]],
            use_container_width=True,
            hide_index=True,
        )
