@echo off
cd /d "%~dp0"

:loop
call ".venv\Scripts\activate.bat"
streamlit run app.py --server.address 0.0.0.0 --server.port 9000
timeout /t 5 /nobreak >nul
goto loop
