# -*- coding: utf-8 -*-
"""
브이월드 국가중점데이터API - 부동산중개업사무소정보조회(getEBOfficeInfo) 클라이언트.
https://api.vworld.kr/ned/data/getEBOfficeInfo

인증키는 코드에 넣지 않고 data/vworld_secrets.json 에서 읽습니다.
(data/vworld_secrets.example.json 을 복사해서 만들고 key/domain 값을 채워주세요)
"""
import json
import os
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_FILE = os.path.join(BASE_DIR, "data", "vworld_secrets.json")
API_URL = "https://api.vworld.kr/ned/data/getEBOfficeInfo"

# 상태구분코드 → 이름 (API 문서 기준)
STATUS_NAMES = {
    "1": "영업중",
    "2": "휴업",
    "3": "휴업연장",
    "4": "실효",
    "6": "전출",
    "7": "등록취소",
    "8": "업무정지",
}

# 개요 화면에서 쓸 큰 분류 (실효/전출/등록취소는 사실상 폐업으로 묶음)
STATUS_CATEGORY = {
    "1": "active",
    "2": "pause",
    "3": "ext",
    "8": "stop",
    "4": "closed",
    "6": "closed",
    "7": "closed",
}


def load_credentials() -> dict:
    if not os.path.exists(SECRETS_FILE):
        raise SystemExit(
            f"[안내] {SECRETS_FILE} 파일이 없습니다.\n"
            f"       data/vworld_secrets.example.json 을 복사해 data/vworld_secrets.json 으로 만들고\n"
            f"       발급받은 key(및 필요시 domain) 값을 채워주세요."
        )
    with open(SECRETS_FILE, encoding="utf-8") as f:
        creds = json.load(f)
    if not creds.get("key"):
        raise SystemExit("[안내] data/vworld_secrets.json 의 key 값이 비어 있습니다.")
    return creds


def status_category(code) -> str:
    return STATUS_CATEGORY.get(str(code), "unknown")


def fetch_page(page_no: int, num_of_rows: int = 1000, ld_code: str = None, sttus_se_code: str = None) -> dict:
    creds = load_credentials()
    params = {
        "key": creds["key"],
        "format": "json",
        "numOfRows": num_of_rows,
        "pageNo": page_no,
    }
    if creds.get("domain"):
        params["domain"] = creds["domain"]
    if ld_code:
        params["ldCode"] = ld_code
    if sttus_se_code:
        params["sttusSeCode"] = sttus_se_code

    resp = requests.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _extract_fields(payload: dict) -> tuple[list[dict], int]:
    body = payload.get("EDOffices", payload)
    result_code = body.get("resultCode") or ""
    if result_code and result_code not in ("NORMAL_CODE", ""):
        raise SystemExit(f"[API 오류] {result_code}: {body.get('resultMsg', '')}")
    total_count = int(body.get("totalCount", 0) or 0)
    fields = body.get("field") or []
    if isinstance(fields, dict):
        fields = [fields]
    for row in fields:
        # 브이월드 원본 데이터에 시군구명(ldCodeNm) 앞뒤 공백이 섞여 오는 경우가 있어(예: 강원 지역 다수),
        # 같은 지역이 공백 유무로 서로 다른 지역인 것처럼 중복 집계되는 걸 막기 위해 여기서 한 번에 정리한다.
        if row.get("ldCodeNm"):
            row["ldCodeNm"] = row["ldCodeNm"].strip()
    return fields, total_count


def fetch_all(ld_code: str = None, sttus_se_code: str = None, sleep_sec: float = 0.2) -> list[dict]:
    """페이지를 끝까지 순회하며 조건에 맞는 전체 레코드를 리스트로 반환합니다."""
    rows = []
    page_no = 1
    num_of_rows = 1000
    while True:
        payload = fetch_page(page_no, num_of_rows, ld_code, sttus_se_code)
        fields, total_count = _extract_fields(payload)
        rows.extend(fields)

        if not fields or len(rows) >= total_count:
            break
        page_no += 1
        time.sleep(sleep_sec)
    return rows
