@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   AI Agent
echo ============================================
echo.

rem ---- 1. Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Install Python 3.10+ and check "Add Python to PATH".
    echo         https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo [1/3] Python %PYVER%

rem ---- 2. Dependencies ----
python -c "import openpyxl, PIL" >nul 2>nul
if errorlevel 1 (
    echo [2/3] Installing dependencies...
    python -m pip install -e .
    if errorlevel 1 (
        echo.
        echo [ERROR] Install failed. Retry manually:
        echo         python -m pip install -e .
        echo.
        pause
        exit /b 1
    )
) else (
    echo [2/3] Dependencies OK
)

rem ---- 3. Config ----
if not exist "config.ini" (
    if exist "config.ini.example" copy "config.ini.example" "config.ini" >nul
    echo.
    echo ============================================
    echo   API key required
    echo ============================================
    echo.
    echo   File: %CD%\config.ini
    echo.
    echo   Fill in:
    echo.
    echo       [model_reasoning]
    echo       api_key = your-api-key
    echo.
    start "" notepad "config.ini"
    pause
    exit /b 1
)

python -c "import sys;sys.path.insert(0,'.');from agent.config import get_model_reasoning as g;sys.exit(0 if g().get('api_key') else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo ============================================
    echo   API key not set
    echo ============================================
    echo.
    echo   File: %CD%\config.ini
    echo.
    echo   Fill in:
    echo.
    echo       [model_reasoning]
    echo       api_key = your-api-key
    echo.
    start "" notepad "config.ini"
    pause
    exit /b 1
)

echo [3/3] Config OK
echo.
echo ============================================
echo   URL:    http://127.0.0.1:8765/
echo   Stop:   Ctrl+C
echo ============================================
echo.

python -m agent.entry.web --host 127.0.0.1 --port 8765
pause
