# -*- coding: utf-8 -*-
"""'YYYY-MM' 문자열 기반 월 연산 공용 유틸. 여러 pages_content 모듈(brokers.py, transactions.py 등)에서
MoM/YoY 계산에 공통으로 쓴다."""


def shift_month(ym: str, delta: int) -> str:
    """'2026-09' 같은 월 문자열을 delta개월만큼 이동시킨다 (delta는 음수 가능)."""
    y, m = map(int, ym.split("-"))
    idx = y * 12 + (m - 1) + delta
    y2, m2 = divmod(idx, 12)
    return f"{y2:04d}-{m2 + 1:02d}"


def find_row(series: list[dict], month: str):
    """월별 dict 리스트(각 dict에 '월' 키가 있다고 가정)에서 해당 월의 행을 찾는다."""
    return next((r for r in series if r["월"] == month), None)
