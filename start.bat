@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo   AI Agent
echo ============================================
echo.

rem ---- 1. Find Python 3.10+ ----
set "PY="
for %%C in ("py -3.13" "py -3.12" "py -3.14" "py -3.11" "py -3.10" "py -3.15" "py -3" "python" "python3") do (
    if not defined PY (
        %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY=%%~C"
    )
)

if not defined PY (
    echo [ERROR] Python 3.10+ not found.
    echo         Install it from https://www.python.org/downloads/
    echo         Check "Add python.exe to PATH", then run start.bat again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('%PY% --version 2^>^&1') do set "PYVER=%%V"
echo [1/4] %PYVER%  (%PY%)

rem ---- 2. Ensure pip through Python, never bare pip ----
%PY% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [2/4] pip is missing; trying ensurepip...
    %PY% -m ensurepip --upgrade
    if errorlevel 1 (
        echo.
        echo [ERROR] pip could not be installed. Reinstall Python 3.10+.
        echo.
        pause
        exit /b 1
    )
)
echo [2/4] pip is ready

rem ---- 3. Dependencies ----
%PY% -c "import openpyxl, PIL, et_xmlfile" >nul 2>&1
if errorlevel 1 (
    echo [3/4] Installing dependencies...
    %PY% -m pip install -e . -c constraints.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Dependency install failed. Retry:
        echo         %PY% -m pip install -e . -c constraints.txt
        echo.
        pause
        exit /b 1
    )
) else (
    echo [3/4] Runtime dependencies are ready
)

%PY% -c "import edge_tts; from importlib.metadata import version; v=version('edge-tts').split('.'); raise SystemExit(0 if (int(v[0]), int(v[1]), int(v[2])) >= (7, 3, 1) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [3/4] Installing or upgrading speech dependency...
    %PY% -m pip install -e ".[tts]" -c constraints.txt
    if errorlevel 1 echo [WARN] edge-tts missing or too old; AI speech will be unavailable.
)

rem ---- 4. Configuration is handled by the settings page ----
echo [4/4] Configuration is handled by the settings page
echo.

echo ============================================
echo   URL:    http://127.0.0.1:8765/
echo   Stop:   Ctrl+C
echo ============================================
echo.

%PY% -m agent.entry.web --host 127.0.0.1 --port 8765 --open
pause
