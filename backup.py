# -*- coding: utf-8 -*-
"""
매일 수집이 끝난 뒤 일별 통계 엑셀 파일을 data/backups/ 밑에 복사해 둔다.
디스크가 무한정 커지지 않도록 오래된 백업 폴더는 자동으로 정리한다.
(원래 offices.db(SQLite)도 같이 백업했으나, 데이터를 Supabase로 옮긴 뒤로는
로컬에 그 파일이 갱신되지 않아 백업 대상에서 뺐다. DB 백업은 Supabase 쪽 기능에 맡긴다.)
"""
import os
import shutil
import sys
from datetime import date, timedelta

import excel_export

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "backups")
RETENTION_DAYS = 30  # 이보다 오래된 백업 폴더는 자동 삭제


def backup_now(today: str = None) -> str:
    """data/backups/YYYY-MM-DD/ 폴더에 엑셀 파일을 복사한다."""
    today = today or date.today().isoformat()
    target_dir = os.path.join(BACKUP_DIR, today)
    os.makedirs(target_dir, exist_ok=True)

    if os.path.exists(excel_export.EXCEL_FILE):
        shutil.copy2(excel_export.EXCEL_FILE, os.path.join(target_dir, os.path.basename(excel_export.EXCEL_FILE)))

    _prune_old_backups()
    return target_dir


def _prune_old_backups(retention_days: int = RETENTION_DAYS):
    if not os.path.isdir(BACKUP_DIR):
        return
    cutoff = date.today() - timedelta(days=retention_days)
    for name in os.listdir(BACKUP_DIR):
        path = os.path.join(BACKUP_DIR, name)
        if not os.path.isdir(path):
            continue
        try:
            folder_date = date.fromisoformat(name)
        except ValueError:
            continue
        if folder_date < cutoff:
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    path = backup_now()
    print(f"백업 완료: {path}", file=sys.stderr)
