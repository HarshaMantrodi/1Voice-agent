@echo off
title 🏥 Hospital Voice Agent
color 0A
cls
echo.
echo  ============================================
echo    Hospital Voice Agent  -  Starting Now...
echo  ============================================
echo.
echo  Your browser will open automatically.
echo  If it does not, open Chrome and go to:
echo  http://localhost:8080
echo.
echo  Press Ctrl+C to stop the server.
echo  ============================================
echo.
cd /d "%~dp0"

:: Try python first, then python3
python --version >nul 2>&1
if %errorlevel% == 0 (
    python app.py
) else (
    python3 --version >nul 2>&1
    if %errorlevel% == 0 (
        python3 app.py
    ) else (
        echo  ERROR: Python is not installed.
        echo  Please install Python from https://python.org
        echo  and try again.
        pause
    )
)
pause
