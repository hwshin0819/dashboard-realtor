# -*- coding: utf-8 -*-
"""
매일 1회 실행하는 수집기.
- 브이월드 getEBOfficeInfo 에서 조회 가능한 4개 상태(영업중/휴업/휴업연장/업무정지)를 전국 단위로 전부 받아온다.
- 어제 저장된 offices 테이블과 비교해서 개업/폐업/상태전환 이벤트를 만든다.
  (등록취소·실효·전출 상태는 API가 아예 목록에서 빼버리므로, 폐업은 "어제 있었는데 오늘 없어짐"으로 판정한다)
- 첫 실행(부트스트랩)은 비교 대상이 없으므로 이벤트를 만들지 않고 현재 상태만 저장한다.
"""
import sys
from collections import defaultdict
from datetime import date

import backup
import db
import excel_export
import vworld_client as vc

QUERYABLE_STATUS_CODES = ["1", "2", "3", "8"]  # 영업중/휴업/휴업연장/업무정지


def pull_snapshot() -> dict:
    """오늘 시점 전국 스냅샷을 jurirno -> record 딕셔너리로 반환."""
    snapshot = {}
    for code in QUERYABLE_STATUS_CODES:
        rows = vc.fetch_all(sttus_se_code=code)
        for r in rows:
            jurirno = r.get("jurirno")
            if jurirno:
                snapshot[jurirno] = r
    return snapshot


def run_daily_collection(today: str = None) -> dict:
    today = today or date.today().isoformat()
    conn = db.get_conn()

    already_done = conn.execute(
        "SELECT 1 FROM collection_log WHERE collected_date=?", (today,)
    ).fetchone()
    if already_done:
        conn.close()
        return {"skipped": True, "reason": f"{today} 는 이미 수집되었습니다."}

    is_bootstrap = conn.execute("SELECT COUNT(*) FROM offices").fetchone()[0] == 0

    snapshot = pull_snapshot()

    # 사무소마다 SELECT를 개별로 날리면(예전 SQLite에선 무시할 만했지만) 네트워크 너머 DB에서는
    # 10만 건 넘는 건수만큼 왕복 지연이 그대로 곱해져 수십 분씩 걸린다. 기존 전체를 한 번에 읽어
    # 메모리에서 대조하고, 쓰기도 아래에서 한꺼번에 묶어 보낸다.
    existing_rows = conn.execute("SELECT jurirno, sttus_se_code, closed_date FROM offices").fetchall()
    existing_map = {row["jurirno"]: (row["sttus_se_code"], row["closed_date"]) for row in existing_rows}
    prev_status = {jurirno: st for jurirno, (st, closed) in existing_map.items() if closed is None}

    opened = closed = status_changed = 0
    opened_by_region = defaultdict(int)
    closed_by_region = defaultdict(int)

    new_office_rows = []
    update_office_rows = []
    event_rows = []

    for jurirno, r in snapshot.items():
        ld_code = r.get("ldCode")
        ld_code_nm = r.get("ldCodeNm")
        bsnm = r.get("bsnmCmpnm")
        new_status = r.get("sttusSeCode")

        existing = existing_map.get(jurirno)

        if existing is None:
            new_office_rows.append((
                jurirno, ld_code, ld_code_nm, bsnm, r.get("brkrNm"), new_status, r.get("sttusSeCodeNm"),
                r.get("registDe"), r.get("estbsBeginDe"), r.get("estbsEndDe"), r.get("lastUpdtDt"),
                r.get("mnnmadr"), r.get("rdnmadr"), r.get("rdnmadrcode"),
                today, today,
            ))
            if not is_bootstrap:
                event_rows.append((today, jurirno, "open", None, new_status, ld_code, ld_code_nm, bsnm))
                opened += 1
                opened_by_region[ld_code_nm] += 1
        else:
            old_status, old_closed_date = existing
            was_closed = old_closed_date is not None

            update_office_rows.append((
                jurirno, ld_code, ld_code_nm, bsnm, r.get("brkrNm"), new_status, r.get("sttusSeCodeNm"),
                r.get("registDe"), r.get("estbsBeginDe"), r.get("estbsEndDe"), r.get("lastUpdtDt"),
                r.get("mnnmadr"), r.get("rdnmadr"), r.get("rdnmadrcode"), today,
            ))
            if not is_bootstrap:
                if was_closed:
                    event_rows.append((today, jurirno, "open", old_status, new_status, ld_code, ld_code_nm, bsnm))
                    opened += 1
                    opened_by_region[ld_code_nm] += 1
                elif old_status is not None and old_status != new_status:
                    event_rows.append((today, jurirno, "status_change", old_status, new_status, ld_code, ld_code_nm, bsnm))
                    status_changed += 1

    if new_office_rows:
        conn.execute_values(
            """INSERT INTO offices
               (jurirno, ld_code, ld_code_nm, bsnm_cmpnm, brkr_nm, sttus_se_code, sttus_se_code_nm,
                regist_de, estbs_begin_de, estbs_end_de, last_updt_dt, mnnmadr, rdnmadr, rdnmadr_code,
                first_seen_date, last_seen_date)
               VALUES %s""",
            new_office_rows,
        )

    if update_office_rows:
        conn.execute_values(
            """UPDATE offices AS o SET
                   ld_code=v.ld_code, ld_code_nm=v.ld_code_nm, bsnm_cmpnm=v.bsnm_cmpnm, brkr_nm=v.brkr_nm,
                   sttus_se_code=v.sttus_se_code, sttus_se_code_nm=v.sttus_se_code_nm,
                   regist_de=v.regist_de, estbs_begin_de=v.estbs_begin_de, estbs_end_de=v.estbs_end_de,
                   last_updt_dt=v.last_updt_dt, mnnmadr=v.mnnmadr, rdnmadr=v.rdnmadr, rdnmadr_code=v.rdnmadr_code,
                   last_seen_date=v.last_seen_date, closed_date=NULL
               FROM (VALUES %s) AS v(jurirno, ld_code, ld_code_nm, bsnm_cmpnm, brkr_nm, sttus_se_code,
                                      sttus_se_code_nm, regist_de, estbs_begin_de, estbs_end_de, last_updt_dt,
                                      mnnmadr, rdnmadr, rdnmadr_code, last_seen_date)
               WHERE o.jurirno = v.jurirno""",
            update_office_rows,
        )

    if event_rows:
        conn.execute_values(
            """INSERT INTO events (event_date, jurirno, event_type, from_status, to_status, ld_code, ld_code_nm, bsnm_cmpnm)
               VALUES %s""",
            event_rows,
        )

    # 어제까지 살아있었는데 오늘 스냅샷에 없는 것 -> 폐업 처리
    if not is_bootstrap:
        missing = set(prev_status) - set(snapshot)
        for jurirno in missing:
            row = conn.execute(
                "SELECT ld_code, ld_code_nm, bsnm_cmpnm, sttus_se_code FROM offices WHERE jurirno=?", (jurirno,)
            ).fetchone()
            conn.execute("UPDATE offices SET closed_date=? WHERE jurirno=?", (today, jurirno))
            conn.execute(
                """INSERT INTO events (event_date, jurirno, event_type, from_status, to_status, ld_code, ld_code_nm, bsnm_cmpnm)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (today, jurirno, "close", row["sttus_se_code"], None, row["ld_code"], row["ld_code_nm"], row["bsnm_cmpnm"]),
            )
            closed += 1
            closed_by_region[row["ld_code_nm"]] += 1

    counts = {"1": 0, "2": 0, "3": 0, "8": 0}
    for r in snapshot.values():
        code = r.get("sttusSeCode")
        if code in counts:
            counts[code] += 1

    conn.execute(
        """INSERT OR REPLACE INTO collection_log
           (collected_date, total_active, total_pause, total_ext, total_stop, collected_at)
           VALUES (?,?,?,?,?, datetime('now', 'localtime'))""",
        (today, counts["1"], counts["2"], counts["3"], counts["8"]),
    )

    active_by_region = defaultdict(int)
    for r in snapshot.values():
        if r.get("sttusSeCode") == "1":
            active_by_region[r.get("ldCodeNm")] += 1

    regions = set(active_by_region) | set(opened_by_region) | set(closed_by_region)
    for region in regions:
        conn.execute(
            """INSERT OR REPLACE INTO daily_region_stats (date, region, active, opened, closed)
               VALUES (?,?,?,?,?)""",
            (today, region, active_by_region.get(region, 0), opened_by_region.get(region, 0), closed_by_region.get(region, 0)),
        )

    conn.commit()
    conn.close()

    # DB 반영은 이미 위에서 commit까지 끝났다 — 엑셀 내보내기/백업은 부가 작업이라 여기서 실패해도
    # (예: 엑셀 파일을 누가 열어놓아 PermissionError) 전체를 죽이지 않고 그날 수집 자체는 성공으로 남긴다.
    # 예전엔 이 두 단계에서 예외가 나면 스크립트가 통째로 죽어서, 그 뒤로 몇 주씩 DB 수집·백업이
    # 둘 다 조용히 멈춰있던 적이 있었다.
    try:
        excel_path = excel_export.append_daily_stats(today, active_by_region, opened_by_region, closed_by_region)
    except Exception as e:
        print(f"[경고] 엑셀 내보내기 실패(파일이 열려있을 수 있음): {e}", file=sys.stderr)
        excel_path = None

    try:
        backup_path = backup.backup_now(today)
    except Exception as e:
        print(f"[경고] 백업 실패: {e}", file=sys.stderr)
        backup_path = None

    return {
        "bootstrap": is_bootstrap,
        "total_snapshot": len(snapshot),
        "opened": opened,
        "closed": closed,
        "status_changed": status_changed,
        "status_counts": counts,
        "excel_path": excel_path,
        "backup_path": backup_path,
    }


if __name__ == "__main__":
    result = run_daily_collection()
    print(result, file=sys.stderr)
