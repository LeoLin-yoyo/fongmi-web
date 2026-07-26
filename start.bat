@echo off
chcp 65001 >nul 2>&1
cd /d %~dp0
echo ========================================
echo   FongMi TV Web
echo ========================================
echo [启动] http://localhost:8000
echo.
start "" "http://localhost:8000"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
pause