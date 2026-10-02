@echo off
chcp 65001 >nul 2>&1
cd /d %~dp0
echo ========================================
echo   FongMi TV Web
echo ========================================
echo [启动] 本机访问 http://localhost:8000
echo [启动] 局域网访问 http://%COMPUTERNAME%:8000 (或用本机局域网 IP)
echo.
start "" "http://localhost:8000"
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause