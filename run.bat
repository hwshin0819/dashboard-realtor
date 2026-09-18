@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  중개사무소 개폐업 대시보드 - 설치 및 실행
echo ============================================
echo.

set "PYEXE="
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYEXE=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYEXE=python"
    )
)

if "%PYEXE%"=="" (
    echo [오류] 이 컴퓨터에서 Python을 찾을 수 없습니다.
    echo https://www.python.org/downloads/ 에서 Python을 설치한 뒤
    echo 설치 중 "Add python.exe to PATH" 항목에 반드시 체크하고 다시 실행해주세요.
    echo.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/3] 처음 실행이라 파이썬 가상환경을 만듭니다. 잠시만 기다려주세요...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
) else (
    echo [1/3] 기존 가상환경을 사용합니다.
)

call ".venv\Scripts\activate.bat"

echo [2/3] 필요한 패키지를 설치/업데이트합니다. (인터넷 연결이 필요합니다)
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo [오류] 패키지 설치에 실패했습니다. 회사 네트워크/방화벽 정책을 확인해주세요.
    pause
    exit /b 1
)

echo [3/3] 대시보드 서버를 시작합니다.
echo.
echo   내 컴퓨터에서 접속:      http://localhost:9000
echo   같은 사무실 네트워크에서: http://192.168.14.117:9000
echo.
echo   창을 닫으면 서버가 종료됩니다. 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo   (처음 실행 시 Windows 보안 경고가 뜨면 "액세스 허용"을 눌러주세요)
echo.

streamlit run app.py --server.address 0.0.0.0 --server.port 9000

echo.
echo 서버가 종료되었습니다.
pause
