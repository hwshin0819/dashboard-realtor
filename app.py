# -*- coding: utf-8 -*-

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
    ai_agent,
)

st.set_page_config(
    page_title="이실장 사업팀 대시보드", 
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

nav_items = list(auth.ALL_PAGES)
if auth.is_admin():
    nav_items += [auth.PAGE_ACCESS_LOG, auth.PAGE_ADMIN]
    user_allowed.update([auth.PAGE_ADMIN, auth.PAGE_ACCESS_LOG])

fallback_page = next((p for p in nav_items if p in user_allowed), None)

if fallback_page is not None and st.session_state.get("nav_page") not in user_allowed:
    show_dialog = "nav_page" in st.session_state
    st.session_state["nav_page"] = fallback_page
    if show_dialog:
        _no_access_dialog()

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
            f'section[data-testid="stSidebar"] div[role="radiogroup"] > *:nth-child({i}) p'
            for i in disallowed_idx
        )
        st.markdown(f"<style>{selectors} {{ color: {theme.MUTED} !important; }}</style>", unsafe_allow_html=True)

    if auth.is_admin():
        admin_idx = len(auth.ALL_PAGES) + 1
        st.markdown(
            f'<style>section[data-testid="stSidebar"] div[role="radiogroup"] > *:nth-child({admin_idx}) '
            f'{{ margin-top: 12px; padding-top: 12px; border-top: 1px solid {theme.LINE}; }}</style>',
            unsafe_allow_html=True,
        )

if selected_page not in user_allowed:
    st.info("접근 가능한 화면이 없습니다. 관리자에게 문의해주세요.")
    st.stop()

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
elif selected_page == auth.PAGE_AI_AGENT:
    ai_agent.render()
elif selected_page == auth.PAGE_BROKERS:
    st.title(auth.PAGE_BROKERS)

    if auth.is_admin():
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
