@echo off
rem ---------------------------------------------------------------
rem  Remove build caches and development scratch folders.
rem  Keeps: dist\ audio_cardpoint.py audio_cardpoint.spec build_exe.*
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo This will delete build caches and test folders:
echo   build\  _build_*  _w*\  _c*\  _probe\  dist2\  dist3\
echo   dist\beatdir\  dist\AudioCardPointDir\
echo.
echo The shipped exe and the source files are NOT touched.
echo.
set /p ANSWER=Continue? [y/N]
if /i not "%ANSWER%"=="y" goto :cancel

call :rmdir build
call :rmdir _build_cache
call :rmdir _build_out
call :rmdir _probe
call :rmdir dist2
call :rmdir dist3
call :rmdir dist\beatdir
call :rmdir dist\AudioCardPointDir

for /d %%d in (_w*) do call :rmdir "%%d"
for /d %%d in (_c*) do call :rmdir "%%d"
for /d %%d in (_build*) do call :rmdir "%%d"

echo.
echo Done.
goto :end

:rmdir
if exist "%1" (
    rd /s /q "%1"
    echo removed %1
)
exit /b

:cancel
echo Cancelled.

:end
endlocal
