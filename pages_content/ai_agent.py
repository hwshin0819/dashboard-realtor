# -*- coding: utf-8 -*-
"""AI 에이전트 — 자연어 질문을 Gemini function-calling으로 데이터 조회로 바꿔 답한다.
범위는 ai_tools.py에 등록된 도구(실거래량 동향/CP 현황/공인중개사 개폐업 현황/중개업 시장 동향)뿐이다."""
import os
import time

import streamlit as st
from google import genai
from google.genai import errors as genai_errors

import ai_tools
import auth
import real_estate_stats as res

MODEL = "gemini-3.8-flash"
# 새로 나온 모델이라 "high demand"(503) 오류가 종종 뜬다 — 실제 코드 문제가 아니라
# 일시적 과부하라 짧게 재시도하면 대부분 넘어간다.
_MAX_RETRIES = 2


@st.cache_resource
def _client():
    """genai.Client는 __del__에서 내부 httpx 커넥션을 닫는다 — 매 rerun마다 새로 만들면
    직전 rerun의 client가 GC되면서 session_state에 남겨둔 chat이 쓰던 커넥션까지 끊겨
    'client has been closed' 오류가 난다. 세션 동안 하나만 만들어 재사용한다."""
    key = os.environ.get("GEMINI_API_KEY")
    return genai.Client(api_key=key) if key else None


def _system_instruction() -> str:
    all_series = res.load_monthly_series("전체", "전체", "전국")
    all_months = [r["월"] for r in all_series]
    if not all_months:
        confirmed, span = "알 수 없음", "데이터 없음"
    else:
        confirmed = all_months[-2] if len(all_months) > 1 else all_months[-1]
        span = f"{all_months[0]}~{all_months[-1]}"
    return (
        "너는 부동산 중개업 대시보드의 데이터 조회 비서다. 제공된 도구(함수)를 호출해서 얻은 "
        "숫자로만 답하고, 도구 결과에 없는 내용은 추측하지 마라. 도구로 답할 수 없는 질문(예: "
        "개발 호재, 시세 전망)이면 모른다고 명확히 말해라. 답은 간결한 한국어로.\n"
        "다룰 수 있는 도메인은 4가지다. (1) 실거래량 동향(매매/전세/월세): get_transaction_trend, "
        "get_jeonse_wolse_summary. (2) CP 현황(경쟁사 매물 검증방식·점유율·구성비교): "
        "get_cp_method_mix, get_cp_market_share, get_cp_composition_breakdown — 이 도메인은 CP사 "
        "이름이 매달 바뀔 수 있어 고정 목록이 없으니, 정확한 CP사명이나 사용 가능한 월을 모르면 "
        "반드시 list_cp_reference_data를 먼저 호출해서 확인한 뒤 다른 CP 도구를 불러라. "
        "(3) 공인중개사 개폐업 현황: get_office_open_close_stats, get_district_open_close_ranking, "
        "get_current_office_status_snapshot. (4) 중개업 시장 동향(시장 규모·지역별 매출·종사자 "
        "인구통계): get_industry_national_trend, get_industry_tam_estimate, get_tasis_snapshot, "
        "get_tasis_trend, get_industry_demographics_trend.\n"
        f"실거래량 동향에서 데이터가 확정된(잠정치 아닌) 마지막 월은 {confirmed}이고, 데이터가 "
        f"존재하는 전체 범위는 {span}이다. '이번 달'/'최근 3개월'/'올해' 같은 상대적 시점은 이 "
        "확정월을 기준으로 계산해서 도구의 start_month/end_month(YYYY-MM)를 채워라. 다른 도메인은 "
        "각 도구가 돌려주는 값 범위를 그대로 따르면 된다.\n"
        f"실거래량 동향에서 지역은 {ai_tools.VALID_REGIONS} 중에서만, 매물 유형은 "
        f"{ai_tools.PROPERTY_TYPES} 중에서만, 거래 유형은 {ai_tools.TRADE_TYPES} 중에서만 골라 호출해라."
    )


def _get_chat(client):
    if st.session_state.get("ai_chat_model") != MODEL:
        st.session_state["ai_chat"] = client.chats.create(
            model=MODEL,
            config={"tools": ai_tools.TOOLS, "system_instruction": _system_instruction()},
        )
        st.session_state["ai_chat_model"] = MODEL
        st.session_state["ai_messages"] = []
    return st.session_state["ai_chat"]


def _extract_calls(chat, before_len: int) -> list:
    """직전 send_message()가 호출한 도구(함수명·인자)를 뽑는다 — 답변 아래 '근거'로 보여준다."""
    calls = []
    for turn in chat.get_history()[before_len:]:
        for part in turn.parts:
            fc = getattr(part, "function_call", None)
            if fc:
                calls.append((fc.name, dict(fc.args)))
    return calls


def _format_calls(calls: list) -> str:
    return " · ".join(
        f"{name}(" + ", ".join(f"{k}={v}" for k, v in args.items()) + ")"
        for name, args in calls
    )


def render():
    st.title(auth.PAGE_AI_AGENT)
    st.caption("실거래량 동향·CP 현황·공인중개사 개폐업 현황·중개업 시장 동향 데이터에 대해 자연어로 물어보세요.")

    client = _client()
    if client is None:
        st.error("GEMINI_API_KEY가 설정되어 있지 않습니다. 프로젝트 루트 `.env`에 키를 추가해주세요.")
        return

    chat = _get_chat(client)
    messages = st.session_state["ai_messages"]

    for m in messages:
        with st.chat_message(m["role"]):
            st.write(m["text"])
            if m.get("calls"):
                st.caption("근거: " + _format_calls(m["calls"]))

    prompt = st.chat_input("예: 서울 아파트 매매 평균가 올해 추이 알려줘")
    if not prompt:
        return

    messages.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    before_len = len(chat.get_history())
    with st.chat_message("assistant"):
        with st.spinner("조회 중..."):
            text = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    resp = chat.send_message(prompt)
                    text = resp.text or "답변을 만들지 못했어요. 다시 물어봐 주세요."
                    break
                except genai_errors.ServerError:
                    if attempt == _MAX_RETRIES:
                        text = "지금 Gemini 서버가 혼잡해서 응답을 못 받았어요. 잠시 후 다시 물어봐 주세요."
                    else:
                        time.sleep(1.5)
                except genai_errors.APIError as e:
                    text = f"Gemini API 오류가 발생했어요: {e.message if hasattr(e, 'message') else e}"
                    break
        calls = _extract_calls(chat, before_len)
        st.write(text)
        if calls:
            st.caption("근거: " + _format_calls(calls))

    messages.append({"role": "assistant", "text": text, "calls": calls})
