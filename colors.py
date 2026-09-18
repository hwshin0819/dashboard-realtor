# -*- coding: utf-8 -*-
"""공통 색상 팔레트 (dataviz 가이드의 categorical 팔레트에서 선택, 라이트 모드 기준)."""

STATUS_COLORS = {
    "개업": "#2a78d6",   # blue
    "영업중": "#1baf7a",  # aqua
    "폐업": "#e34948",   # red
}

STATUS_ORDER = ["개업", "영업중", "폐업"]

# realtor(github pages) 대시보드 느낌의 개업/폐업/순증감 배색
OPEN_COLOR = "#2f9e6e"   # 초록 (개업)
CLOSE_COLOR = "#e2725b"  # 주홍 (폐업)
NET_COLOR = "#2a78d6"    # 파랑 (순증감)
