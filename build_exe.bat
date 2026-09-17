@echo off
rem Build single-file exe for the audio beat marker tool.
rem Requires: .venv created from local Python with numpy / miniaudio / pyinstaller installed.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" build_exe.py
) else (
  python build_exe.py
)
pause
