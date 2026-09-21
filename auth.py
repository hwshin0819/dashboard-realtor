# -*- coding: utf-8 -*-
"""
아주 단순한 아이디/비밀번호 로그인.
- 별도 DB나 외부 라이브러리 없이, 로컬 JSON 파일(data/users.json)에
  '아이디: {이름, 비밀번호 해시, 역할}' 형태로 저장합니다.
- 비밀번호는 원문으로 저장하지 않고 salt + sha256 해시로 저장합니다.
"""
import hashlib
import os
import secrets

import streamlit as st
import streamlit.components.v1 as components

import data_store as ds

DEFAULT_ADMIN_ID = "admin"
DEFAULT_ADMIN_PW = "changeme123"

# 왼쪽 사이드바에 보여줄 상위 메뉴(=앱) 목록. 계정마다 이 중 일부만 보이도록 제한할 수 있다.
# 이 문자열은 사이드바 표시 라벨이자 동시에 data/users.json의 "pages" 배열에 저장되는 값이기도 하다 —
# 값을 바꾸면 기존 계정들의 "pages"도 같이 마이그레이션해야 한다(그래야 allowed_pages()의 교집합이 안 깨짐).
PAGE_INDUSTRY_TRENDS = "중개업 시장 동향"
PAGE_TRANSACTIONS = "실거래량 동향"
PAGE_BROKERS = "공인중개사 현황"
PAGE_CP_STATUS = "CP 현황"
PAGE_CALCULATOR = "공헌이익 시뮬레이터"
ALL_PAGES = [PAGE_INDUSTRY_TRENDS, PAGE_TRANSACTIONS, PAGE_BROKERS, PAGE_CP_STATUS,
             PAGE_CALCULATOR]

# 관리자 전용 메뉴. 계정별 권한 제한 대상이 아니라 역할(admin)로만 노출 여부를 결정한다.
PAGE_ADMIN = "관리자 계정 관리"
PAGE_ACCESS_LOG = "시스템 접속 로그"


def allowed_pages(record: dict) -> list:
    """계정 레코드(users.json의 값)에서 접근 가능한 메뉴 목록을 뽑는다.
    'pages' 키가 아예 없는 기존 계정은 하위호환을 위해 전체 메뉴를 허용한다."""
    pages = record.get("pages")
    if pages is None:
        return list(ALL_PAGES)
    return [p for p in ALL_PAGES if p in pages]


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def make_credential(password: str) -> dict:
    salt = secrets.token_hex(8)
    return {"salt": salt, "hash": _hash_password(password, salt)}


def verify_password(password: str, credential: dict) -> bool:
    if not credential:
        return False
    return _hash_password(password, credential.get("salt", "")) == credential.get("hash")


def ensure_seed_admin():
    """최초 실행 시 관리자 계정이 하나도 없으면 기본 관리자 계정을 만들어 둡니다."""
    users = ds.load_users()
    if not users:
        users[DEFAULT_ADMIN_ID] = {
            "이름": "관리자",
            "역할": "admin",
            "credential": make_credential(DEFAULT_ADMIN_PW),
        }
        ds.save_users(users)
    return users


def current_user():
    return st.session_state.get("user")


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("role") == "admin")


def logout():
    user = current_user()
    if user:
        ds.append_access_log(user["id"], "로그아웃", True, ip=st.context.ip_address or "로컬(localhost)")
    st.session_state.pop("user", None)


def login_gate():
    """
    로그인이 안 되어 있으면 로그인 폼을 그리고 앱 실행을 멈춥니다(st.stop()).
    로그인이 되어 있으면 아무 것도 하지 않고 조용히 통과합니다.
    """
    ensure_seed_admin()

    if current_user():
        return

    st.markdown("<div style='margin-top:4rem;'></div>", unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login_form"):
            user_id = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", use_container_width=True)

        # 아이디에 한글이 타이핑되는 순간 바로 지운다. 계정 아이디는 전부 영문/숫자(admin, 이메일)라
        # 한글이 섞이면 100% 오타이므로, 입력 단계에서부터 막아 헷갈리지 않게 한다.
        # components.html은 iframe이라 window.parent로 실제 로그인 폼의 input에 접근한다.
        components.html(
            """
            <script>
            (function() {
                const HANGUL = /[\\u3131-\\u318E\\uAC00-\\uD7A3]/g;
                function attach() {
                    const input = window.parent.document.querySelector('input[aria-label="아이디"]');
                    if (!input || input.dataset.hangulGuard) return;
                    input.dataset.hangulGuard = "1";
                    const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, "value").set;
                    input.addEventListener("input", function() {
                        const stripped = input.value.replace(HANGUL, "");
                        if (stripped !== input.value) {
                            setter.call(input, stripped);
                            input.dispatchEvent(new Event("input", {bubbles: true}));
                        }
                    });
                }
                const timer = setInterval(attach, 200);
                setTimeout(function() { clearInterval(timer); }, 10000);
            })();
            </script>
            """,
            height=0,
        )

        if submitted:
            client_ip = st.context.ip_address or "로컬(localhost)"
            users = ds.load_users()
            record = users.get(user_id)
            if record and verify_password(password, record.get("credential", {})):
                st.session_state["user"] = {
                    "id": user_id,
                    "name": record.get("이름", user_id),
                    "role": record.get("역할", "user"),
                    "pages": allowed_pages(record),
                }
                ds.append_access_log(user_id, "로그인", True, ip=client_ip)
                st.rerun()
            else:
                ds.append_access_log(user_id or "(빈 아이디)", "로그인", False, note="아이디 또는 비밀번호 불일치", ip=client_ip)
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

    st.stop()
