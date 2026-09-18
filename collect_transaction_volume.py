# -*- coding: utf-8 -*-
"""
국토부 실거래가(아파트/오피스텔/연립다세대/단독다가구 x 매매/전월세) 월별 거래량·평균금액 수집기.

- PublicDataReader.TransactionPrice로 시군구 단위 API를 호출한다 — 이 API는 시군구 단위로만
  조회되므로, "전국 합계"를 보여주려면 시군구(offices 테이블의 ld_code, 약 250개)를 전부 모아야 한다.
- 서비스키의 일일 호출 한도를 모르는 상태이므로, (시군구, 유형, 거래유형, 연월) 조합 하나하나를
  작업 단위로 보고 transaction_collect_progress에 체크포인트를 남기는 재개 가능한(resumable) 배치로
  만들었다. 한 번 실행에 MAX_UNITS_PER_RUN개만 처리하고 멈추며, 다시 실행하면 이어서 처리한다.
- 최근 달 -> 과거 달 순서로, 그리고 같은 달 안에서는 전 지역을 먼저 돈다. 그래야 몇 번만 돌려도
  "최근 N개월 전국" 화면이 먼저 채워지고, START_YM(2020-01)부터의 전체 이력은 이후 실행에서 점점 채워진다.
- API 호출은 스레드풀(MAX_WORKERS개 동시)로 병렬 처리한다. TransactionPrice.get_data()는 매 호출마다
  독립적인 requests.get()만 하고 인스턴스 자체엔 공유 가변 상태가 없어 여러 스레드가 같은 api 객체를
  동시에 써도 안전하다. DB 쓰기(commit)는 항상 메인 스레드에서만 해서 SQLite 동시성 문제를 피한다.
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from datetime import date

from dotenv import load_dotenv

import db
import month_utils as mu

PROPERTY_TYPES = ["아파트", "오피스텔", "연립다세대", "단독다가구"]
TRADE_TYPES = ["매매", "전월세"]
START_YM = "2020-01"  # 이 달부터 오늘까지만 수집 (그 이전은 범위 밖)
MAX_UNITS_PER_RUN = 50000  # 시간 예산이 먼저 걸리도록 충분히 크게(사실상 시간 제한이 주 통제 수단)
MAX_SECONDS_PER_RUN = 50 * 60  # 스케줄러로 주기 실행할 때, 한 번 실행이 너무 길어지지 않게(기본 50분)
MAX_CONSECUTIVE_ERRORS = 8  # 이 이상 실패가 쌓이면(키 오류 등으로 추정) 조기 중단 (병렬이라 살짝 여유를 둠)
MAX_WORKERS = 3  # 동시 호출 수 — 5로 하면 "초당 요청한도" 순간버스트에 자주 걸려서 낮춤
RATE_BURST_RETRIES = 5  # "초당 요청한도 초과"는 그때만 잠깐 쉬면 곧 풀리므로, 재시도로 흡수한다


def _load_service_key() -> str:
    load_dotenv()
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "DATA_GO_KR_SERVICE_KEY가 설정되어 있지 않습니다. 프로젝트 루트의 .env 파일에 "
            "공공데이터포털에서 발급받은 서비스키를 DATA_GO_KR_SERVICE_KEY=... 형태로 넣어주세요."
        )
    return key


def _sigungu_codes(conn) -> list:
    rows = conn.execute(
        "SELECT DISTINCT ld_code, ld_code_nm FROM offices WHERE ld_code IS NOT NULL ORDER BY ld_code"
    ).fetchall()
    return [(r["ld_code"], r["ld_code_nm"]) for r in rows]


def _month_list(start_ym: str) -> list:
    """start_ym부터 오늘이 속한 달까지의 'YYYY-MM' 목록(최근 -> 과거 순)."""
    end = date.today().strftime("%Y-%m")
    y1, m1 = map(int, start_ym.split("-"))
    y2, m2 = map(int, end.split("-"))
    n = (y2 * 12 + m2) - (y1 * 12 + m1) + 1
    return [mu.shift_month(end, -i) for i in range(n)]


def _pending_units(conn, months: list, sigungu: list):
    """(월 최근순 -> 지역 -> 유형 -> 거래유형) 순서로 아직 끝나지 않은 작업 단위를 하나씩 낸다."""
    done = {
        (r["sigungu_code"], r["property_type"], r["trade_type"], r["ym"])
        for r in conn.execute(
            "SELECT sigungu_code, property_type, trade_type, ym FROM transaction_collect_progress WHERE status='done'"
        )
    }
    for ym in months:
        for code, name in sigungu:
            for ptype in PROPERTY_TYPES:
                for ttype in TRADE_TYPES:
                    key = (code, ptype, ttype, ym)
                    if key not in done:
                        yield code, name, ptype, ttype, ym


def _patch_strict_http_errors() -> None:
    """PublicDataReader는 API가 HTTP 200이 아닌 응답(예: 일일 요청한도 초과 429)을 주면
    조용히 print만 하고 '빈 결과(None)'를 돌려준다 — get_data()는 이를 '거래 0건'과 구분하지
    못해 그대로 저장해버린다(실제로 이 버그로 2021-03~2023-06 데이터가 전부 0으로 잘못 기록됐었다).
    HTTP 실패를 예외로 바꿔서 run_backfill()의 에러 처리(재시도 대상, done 처리 안 함)로 넘어가게 한다."""
    from PublicDataReader.PublicDataPortal import molit

    original = molit.TransactionPrice._response_to_item_data

    def strict(self, res, property_type, trade_type, sigungu_code, year_month):
        if res.status_code != 200:
            raise RuntimeError(
                f"HTTP {res.status_code} ({property_type}/{trade_type}/{sigungu_code}/{year_month}): "
                f"{res.text[:200]}"
            )
        return original(self, res, property_type, trade_type, sigungu_code, year_month)

    molit.TransactionPrice._response_to_item_data = strict


class _RateLimiter:
    """'초당 요청한도 초과'는 워커 하나만 잠깐 쉰다고 안 풀린다 — 다른 워커들이 그 사이에도 계속
    쏘고 있으면 초당 호출 수가 안 줄어들기 때문이다. 그래서 두 가지를 같이 한다:
    1) 매 요청 전에 '전체' 워커가 공유하는 최소 간격을 지키게 해서(스로틀) 애초에 순간적으로
       몰리지 않게 하고, 2) 그래도 초과 에러가 나면 전체를 잠깐 같이 멈추는 쿨다운(백오프)을 건다."""

    def __init__(self, min_interval: float = 0.35):
        self._lock = threading.Lock()
        self._blocked_until = 0.0
        self._next_slot = 0.0
        self._min_interval = min_interval

    def wait_turn(self):
        while True:
            with self._lock:
                now = time.monotonic()
                wait_for = max(self._blocked_until, self._next_slot) - now
                if wait_for <= 0:
                    self._next_slot = now + self._min_interval
                    return
            time.sleep(wait_for)

    def trigger_backoff(self, seconds: float):
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)


def _fetch_one(api, property_type: str, trade_type: str, sigungu_code: str, ym: str, limiter: "_RateLimiter"):
    """한 (시군구,유형,거래유형,연월) 조합을 호출해
    (건수, 평균매매가, 평균보증금, 평균월세, 전세건수, 월세건수, 전세평균보증금, 월세평균보증금,
     전세 중 계약갱신청구권 사용 건수)를 반환한다.
    '초당 요청한도 초과(PER_SECOND)'를 만나면 공유 쿨다운으로 전체 워커를 잠깐 세웠다가 재시도한다 —
    이걸 곧바로 run_backfill()의 연속-실패 카운트로 넘기면 8번 만에(병렬이라 1초도 안 걸려) 전체
    실행이 조기 중단돼버리므로, 여기서 먼저 흡수한다."""
    year_month = ym.replace("-", "")
    df = None
    for attempt in range(RATE_BURST_RETRIES + 1):
        limiter.wait_turn()
        try:
            df = api.get_data(
                property_type=property_type, trade_type=trade_type,
                sigungu_code=sigungu_code, year_month=year_month,
            )
            break
        except Exception as e:
            if "PER_SECOND" in str(e) and attempt < RATE_BURST_RETRIES:
                limiter.trigger_backoff(3.0 + attempt * 2)
                continue
            raise
    if df is None or df.empty:
        return 0, None, None, None, 0, 0, None, None, 0

    if trade_type == "매매":
        if "해제여부" in df.columns:
            df = df[df["해제여부"].isna() | (df["해제여부"].astype(str).str.strip() == "")]
        count = len(df)
        avg_price = int(df["거래금액"].mean()) if count and "거래금액" in df.columns else None
        return count, avg_price, None, None, 0, 0, None, None, 0

    count = len(df)
    avg_deposit = int(df["보증금액"].mean()) if count and "보증금액" in df.columns else None

    has_rent_col = "월세금액" in df.columns
    wolse_mask = df["월세금액"] > 0 if has_rent_col else None
    jeonse_rows = df[~wolse_mask] if has_rent_col else df
    wolse_rows = df[wolse_mask] if has_rent_col else df.iloc[0:0]

    count_jeonse = len(jeonse_rows)
    count_wolse = len(wolse_rows)
    avg_deposit_jeonse = int(jeonse_rows["보증금액"].mean()) if count_jeonse and "보증금액" in jeonse_rows.columns else None
    avg_deposit_wolse = int(wolse_rows["보증금액"].mean()) if count_wolse and "보증금액" in wolse_rows.columns else None
    avg_rent = int(wolse_rows["월세금액"].mean()) if count_wolse else None

    count_jeonse_renewal = 0
    if count_jeonse and "갱신요구권사용" in jeonse_rows.columns:
        count_jeonse_renewal = int((jeonse_rows["갱신요구권사용"] == "사용").sum())

    return (
        count, None, avg_deposit, avg_rent, count_jeonse, count_wolse, avg_deposit_jeonse, avg_deposit_wolse,
        count_jeonse_renewal,
    )


def run_backfill(
    max_units: int = MAX_UNITS_PER_RUN, max_seconds: int = MAX_SECONDS_PER_RUN, max_workers: int = MAX_WORKERS,
) -> dict:
    from PublicDataReader import TransactionPrice  # 무거운 의존성이라 실제 실행 시점에만 임포트

    _patch_strict_http_errors()
    service_key = _load_service_key()
    api = TransactionPrice(service_key)

    conn = db.get_conn()
    months = _month_list(START_YM)
    sigungu = _sigungu_codes(conn)
    if not sigungu:
        conn.close()
        raise RuntimeError("offices 테이블에 시군구 코드가 없습니다. 개폐업 수집(collector.py)을 먼저 실행해주세요.")

    units_iter = _pending_units(conn, months, sigungu)
    limiter = _RateLimiter()
    start_time = time.monotonic()
    processed = 0
    errors = 0
    consecutive_errors = 0
    stopped_early = False
    timed_out = False
    keep_submitting = True

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        in_flight = {}

        def try_submit() -> bool:
            nonlocal keep_submitting
            if not keep_submitting:
                return False
            for unit in units_iter:
                code, name, ptype, ttype, ym = unit
                fut = executor.submit(_fetch_one, api, ptype, ttype, code, ym, limiter)
                in_flight[fut] = unit
                return True
            keep_submitting = False
            return False

        for _ in range(max_workers):
            if not try_submit():
                break

        while in_flight:
            done, _ = wait(list(in_flight.keys()), return_when=FIRST_COMPLETED)
            for fut in done:
                code, name, ptype, ttype, ym = in_flight.pop(fut)
                try:
                    (
                        count, avg_price, avg_deposit, avg_rent,
                        count_jeonse, count_wolse, avg_deposit_jeonse, avg_deposit_wolse,
                        count_jeonse_renewal,
                    ) = fut.result()
                    conn.execute(
                        """INSERT OR REPLACE INTO transaction_monthly
                           (ym, sigungu_code, property_type, trade_type, count, avg_price, avg_deposit, avg_rent,
                            count_jeonse, count_wolse, avg_deposit_jeonse, avg_deposit_wolse, count_jeonse_renewal)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            ym, code, ptype, ttype, count, avg_price, avg_deposit, avg_rent,
                            count_jeonse, count_wolse, avg_deposit_jeonse, avg_deposit_wolse, count_jeonse_renewal,
                        ),
                    )
                    conn.execute(
                        """INSERT OR REPLACE INTO transaction_collect_progress
                           (sigungu_code, property_type, trade_type, ym, status, updated_at)
                           VALUES (?,?,?,?, 'done', datetime('now','localtime'))""",
                        (code, ptype, ttype, ym),
                    )
                    conn.commit()
                    consecutive_errors = 0
                except Exception as e:
                    errors += 1
                    consecutive_errors += 1
                    print(f"[오류] {name}({code}) {ptype} {ttype} {ym}: {e}", file=sys.stderr)
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS and not stopped_early:
                        print(
                            f"[중단] 실패가 {MAX_CONSECUTIVE_ERRORS}건 쌓임 — 서비스키/네트워크 문제로 보여 "
                            "새 요청 제출을 멈춥니다(이미 시작된 요청은 마저 처리).",
                            file=sys.stderr,
                        )
                        stopped_early = True
                        keep_submitting = False
                processed += 1
                if processed >= max_units:
                    keep_submitting = False
                if time.monotonic() - start_time >= max_seconds:
                    timed_out = True
                    keep_submitting = False

            if keep_submitting:
                while len(in_flight) < max_workers:
                    if not try_submit():
                        break

    remaining = 0 if stopped_early else sum(1 for _ in _pending_units(conn, months, sigungu))
    conn.close()
    return {
        "processed": processed, "errors": errors, "elapsed_sec": round(time.monotonic() - start_time, 1),
        "stopped_early": stopped_early, "timed_out": timed_out, "remaining_at_least": remaining,
    }


if __name__ == "__main__":
    result = run_backfill()
    print(result, file=sys.stderr)
