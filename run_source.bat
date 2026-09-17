@echo off
rem ---------------------------------------------------------------------
rem  Run BeatMark directly from source (no packaging needed).
rem  First run: creates .venv and installs numpy + miniaudio automatically.
rem  Usage: double-click, or:  run_source.bat --selftest song.mp3
rem ---------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe

if not exist "%PY%" (
    echo [1/3] Creating virtual environment .venv ...
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   Python not found. Install Python 3.8+ first:
        echo   https://www.python.org/downloads/   ^(tick "Add python.exe to PATH"^)
        echo.
        pause
        exit /b 1
    )
    python -m venv .venv
    if errorlevel 1 (
        echo   Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [2/3] Checking dependencies ...
"%PY%" -c "import numpy, miniaudio" >nul 2>nul
if errorlevel 1 (
    echo   Installing numpy + miniaudio ...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo   Install failed. Check your network / pip source, then retry.
        pause
        exit /b 1
    )
)

echo [3/3] Starting beatmark.py ...
"%PY%" beatmark.py %*
if errorlevel 1 (
    echo.
    echo   The program exited with an error, see the message above.
    pause
)
endlocal
