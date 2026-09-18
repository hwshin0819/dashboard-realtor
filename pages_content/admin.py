# -*- coding: utf-8 -*-
"""관리자 관리 탭: 대시보드에 로그인할 수 있는 계정을 관리합니다."""
import pandas as pd
import streamlit as st

import auth
import data_store as ds


def render():
    st.subheader(auth.PAGE_ADMIN)

    if not auth.is_admin():
        st.info("이 화면은 관리자(admin) 권한 계정만 볼 수 있습니다.")
        return

    st.caption("대시보드에 로그인할 수 있는 사내 계정 목록입니다. 여기서 추가한 사람만 대시보드를 볼 수 있습니다.")

    users = ds.load_users()
    current_id = auth.current_user()["id"]

    table_rows = [
        {
            "아이디": uid,
            "이름": info.get("이름", ""),
            "역할": info.get("역할", "user"),
            "접근 가능 메뉴": ", ".join(auth.allowed_pages(info)),
        }
        for uid, info in users.items()
    ]
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**새 계정 추가**")
    with st.form("add_user_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        new_id = c1.text_input("아이디")
        new_name = c2.text_input("이름")
        new_pw = c3.text_input("초기 비밀번호", type="password")
        new_role = c4.selectbox("역할", ["user", "admin"])
        new_pages = st.multiselect("접근 가능 메뉴", auth.ALL_PAGES, default=auth.ALL_PAGES)
        add_submitted = st.form_submit_button("계정 추가", type="primary", use_container_width=True)

    if add_submitted:
        if not new_id or not new_pw:
            st.error("아이디와 초기 비밀번호는 반드시 입력해야 합니다.")
        elif new_id in users:
            st.error("이미 존재하는 아이디입니다.")
        else:
            users[new_id] = {
                "이름": new_name or new_id,
                "역할": new_role,
                "credential": auth.make_credential(new_pw),
                "pages": new_pages,
            }
            ds.save_users(users)
            st.success(f"'{new_id}' 계정을 추가했습니다.")
            st.rerun()

    st.divider()
    st.markdown("**화면 접근 권한 변경**")
    st.caption("계정마다 왼쪽 메뉴에서 어떤 화면을 볼 수 있는지 제한합니다.")
    with st.form("page_perm_form"):
        perm_target = st.selectbox("대상 계정", list(users.keys()), key="perm_target")
        current_pages = auth.allowed_pages(users.get(perm_target, {}))
        perm_pages = st.multiselect("접근 가능 메뉴", auth.ALL_PAGES, default=current_pages, key="perm_pages")
        perm_submitted = st.form_submit_button("권한 저장", use_container_width=True)

    if perm_submitted:
        if not perm_pages:
            st.error("최소 1개 이상의 메뉴는 허용해야 합니다.")
        else:
            users[perm_target]["pages"] = perm_pages
            ds.save_users(users)
            st.success(f"'{perm_target}' 계정의 접근 권한을 저장했습니다.")
            st.rerun()

    st.divider()
    st.markdown("**비밀번호 재설정**")
    with st.form("reset_pw_form", clear_on_submit=True):
        target_id = st.selectbox("대상 계정", list(users.keys()), key="reset_target")
        new_pw2 = st.text_input("새 비밀번호", type="password", key="reset_pw")
        reset_submitted = st.form_submit_button("비밀번호 재설정", use_container_width=True)

    if reset_submitted:
        if not new_pw2:
            st.error("새 비밀번호를 입력해주세요.")
        else:
            users[target_id]["credential"] = auth.make_credential(new_pw2)
            ds.save_users(users)
            st.success(f"'{target_id}' 계정의 비밀번호를 재설정했습니다.")

    st.divider()
    st.markdown("**계정 삭제**")
    admin_count = sum(1 for u in users.values() if u.get("역할") == "admin")
    del_col1, del_col2 = st.columns([2, 1])
    with del_col1:
        del_target = st.selectbox("삭제할 계정", list(users.keys()), key="del_target")
        confirm = st.checkbox(f"'{del_target}' 계정을 정말 삭제합니다.", key="del_confirm")
    with del_col2:
        st.write("")
        st.write("")
        if st.button("계정 삭제", type="secondary", use_container_width=True):
            if del_target == current_id:
                st.error("현재 로그인한 계정은 삭제할 수 없습니다.")
            elif users[del_target].get("역할") == "admin" and admin_count <= 1:
                st.error("마지막 남은 관리자 계정은 삭제할 수 없습니다.")
            elif not confirm:
                st.error("삭제 확인 체크박스를 선택해주세요.")
            else:
                del users[del_target]
                ds.save_users(users)
                st.success(f"'{del_target}' 계정을 삭제했습니다.")
                st.rerun()
