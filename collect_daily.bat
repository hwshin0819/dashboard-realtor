@echo off
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python collector.py >> data\collect_history.log 2>&1
