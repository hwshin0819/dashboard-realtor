@echo off
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python collect_transaction_volume.py >> data\transaction_collect_history.log 2>&1
