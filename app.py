# -*- coding: utf-8 -*-
"""
이실장 사업팀 대시보드
- 공공데이터(브이월드 등)를 활용해 중개사무소 개업/폐업/영업중 현황을 월별·지역별로 보여주는 대시보드
- 지금 단계는 '틀(UI) + 목업 데이터' 버전입니다. 실제 데이터 수집 연동은 이후 단계에서 진행합니다.
"""
import streamlit as st
import streamlit.components.v1 as components

import auth
import theme
from pages_content import (
    brokers,
    cp_status,
    transactions,
    industry_trends,
    webhooks,
    targets,
    collect_test,
    schedule,
    admin,
    access_log,
    calculator,
)

st.set_page_config(
    page_title="이실장 사업팀 대시보드",  # 브라우저 탭 제목 전용. 로그인 화면·좌측 메뉴 표기는 auth.PAGE_BROKERS를 따로 쓴다.
    layout="wide",
)
theme.inject()


@st.dialog("접근 권한 안내")
def _no_access_dialog():
    st.write("🚫 접근 권한이 없는 메뉴입니다.")
    if st.button("확인", use_container_width=True):
        st.rerun()

# ---- 로그인 확인 (로그인 안 되어 있으면 여기서 멈춤) ----
auth.login_gate()

user = auth.current_user()
pages = user.get("pages") or auth.ALL_PAGES
user_allowed = set(pages)

# 메뉴는 권한과 무관하게 항상 전체를 보여주고, 접근 권한이 없는 항목만 회색으로 표시한다
# (관리자 관리 / 접속 로그는 계정별 권한 대상이 아니라 관리자에게만 항상 보이는 메뉴다).
nav_items = list(auth.ALL_PAGES)
if auth.is_admin():
    nav_items += [auth.PAGE_ADMIN, auth.PAGE_ACCESS_LOG]
    user_allowed.update([auth.PAGE_ADMIN, auth.PAGE_ACCESS_LOG])

fallback_page = next((p for p in nav_items if p in user_allowed), None)

# 권한 없는 항목을 클릭해서 세션에 저장돼 있다면(직전 선택), 위젯을 그리기 전에 허용된 화면으로 되돌린다.
# (위젯이 만들어진 뒤에 session_state를 바꾸면 오류가 나므로 반드시 st.radio 호출 전에 처리해야 한다.)
if fallback_page is not None and st.session_state.get("nav_page") not in user_allowed:
    show_dialog = "nav_page" in st.session_state
    st.session_state["nav_page"] = fallback_page
    if show_dialog:
        _no_access_dialog()

# ---- 사이드바: 계정 정보 + 메뉴(전체 메뉴를 보여주되, 권한 없는 항목은 회색 처리) ----
with st.sidebar:
    st.markdown(f"**{user['name']}** 님으로 로그인됨")
    st.caption(f"아이디: {user['id']} · 역할: {user['role']}")
    if st.button("로그아웃", use_container_width=True):
        auth.logout()
        st.rerun()
    st.divider()
    if len(nav_items) > 1:
        selected_page = st.radio("메뉴", nav_items, key="nav_page", label_visibility="collapsed")
    else:
        selected_page = nav_items[0] if nav_items else None

    disallowed_idx = [i + 1 for i, p in enumerate(nav_items) if p not in user_allowed]
    if disallowed_idx:
        selectors = ", ".join(
            f'section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child({i}) p'
            for i in disallowed_idx
        )
        st.markdown(f"<style>{selectors} {{ color: {theme.MUTED} !important; }}</style>", unsafe_allow_html=True)

    # 관리자 전용 메뉴(관리자 계정 관리/시스템 접속 로그) 앞에 구분선을 넣어 일반 메뉴와 시각적으로 나눈다.
    if auth.is_admin():
        admin_idx = len(auth.ALL_PAGES) + 1
        st.markdown(
            f'<style>section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child({admin_idx}) '
            f'{{ margin-top: 12px; padding-top: 12px; border-top: 1px solid {theme.LINE}; }}</style>',
            unsafe_allow_html=True,
        )

if selected_page not in user_allowed:
    st.info("접근 가능한 화면이 없습니다. 관리자에게 문의해주세요.")
    st.stop()

# 메뉴를 바꿨을 때, 이전 화면에서 스크롤을 내려둔 상태 그대로라 새 화면의 제목이
# 화면 위로 잘려 보이는 문제가 있었다 (탭과 달리 사이드바 메뉴 전환은 자동으로 맨 위로
# 스크롤해주지 않기 때문). 메뉴가 실제로 바뀐 시점에만 맨 위로 스크롤해준다.
if st.session_state.get("_active_page") != selected_page:
    st.session_state["_active_page"] = selected_page
    components.html(
        """
        <script>
        (function(){
            var doc = window.parent.document;
            var main = doc.querySelector('section.main') || doc.querySelector('[data-testid="stAppViewContainer"]');
            if (main) { main.scrollTo(0, 0); }
            window.parent.scrollTo(0, 0);
        })();
        </script>
        """,
        height=0,
    )

if selected_page == auth.PAGE_CALCULATOR:
    calculator.render()
elif selected_page == auth.PAGE_ADMIN:
    admin.render()
elif selected_page == auth.PAGE_ACCESS_LOG:
    access_log.render()
elif selected_page == auth.PAGE_TRANSACTIONS:
    transactions.render()
elif selected_page == auth.PAGE_INDUSTRY_TRENDS:
    industry_trends.render()
elif selected_page == auth.PAGE_CP_STATUS:
    cp_status.render()
elif selected_page == auth.PAGE_BROKERS:
    st.title(auth.PAGE_BROKERS)

    if auth.is_admin():
        TAB_NAMES = ["개요", "웹훅 관리", "수집 대상", "수집테스트", "배치 스케줄"]
        tabs = st.tabs(TAB_NAMES)

        with tabs[0]:
            brokers.render()
        with tabs[1]:
            webhooks.render()
        with tabs[2]:
            targets.render()
        with tabs[3]:
            collect_test.render()
        with tabs[4]:
            schedule.render()
    else:
        brokers.render()
