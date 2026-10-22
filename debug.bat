@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Squint - debug
rem Runs the app with a console attached, so any error is visible instead of
rem being swallowed. Use this if the app misbehaves, then send the output.
rem  The installer puts Python straight into .venv; setup.bat makes a
rem  virtual environment with it under .venv\Scripts. Either is fine.
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=.venv\python.exe"
if not exist "%PY%" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
echo Starting Squint with output shown. Close this window to quit.
echo ---------------------------------------------------------------
"%PY%" "%CD%\run_app.py"
echo ---------------------------------------------------------------
echo App exited with code %errorlevel%.
pause
exit /b 0
