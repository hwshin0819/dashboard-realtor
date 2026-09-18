# -*- coding: utf-8 -*-
"""접속 로그 탭."""
import pandas as pd
import streamlit as st

import auth
import data_store as ds


def render():
    st.subheader(auth.PAGE_ACCESS_LOG)
    st.caption("대시보드 로그인/로그아웃 기록입니다.")

    rows = ds.load_access_log()
    if not rows:
        st.info("아직 기록된 접속 로그가 없습니다.")
        return

    df = pd.DataFrame(rows)
    df["시각"] = pd.to_datetime(df["시각"])
    if "IP" not in df.columns:
        df["IP"] = "-"
    df["IP"] = df["IP"].fillna("-")

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        users = ["(전체)"] + sorted(df["아이디"].unique().tolist())
        user_filter = st.selectbox("아이디로 필터", users)
    with c2:
        result_filter = st.selectbox("결과로 필터", ["(전체)", "성공", "실패"])
    with c3:
        ips = ["(전체)"] + sorted(df["IP"].unique().tolist())
        ip_filter = st.selectbox("IP로 필터", ips)

    filtered = df.copy()
    if user_filter != "(전체)":
        filtered = filtered[filtered["아이디"] == user_filter]
    if result_filter != "(전체)":
        filtered = filtered[filtered["결과"] == result_filter]
    if ip_filter != "(전체)":
        filtered = filtered[filtered["IP"] == ip_filter]

    st.dataframe(
        filtered.sort_values("시각", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(f"총 {len(filtered)}건 표시 중 (전체 {len(df)}건)")
