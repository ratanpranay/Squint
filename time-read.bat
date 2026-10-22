@echo off
setlocal EnableExtensions
title Squint - where the reading time goes
cd /d "%~dp0"

rem  Times each stage of a screen read against the copy of Squint already
rem  installed here. Changes nothing, installs nothing, needs no new build.
rem  Open the page you want to test BEFORE running this - it reads the
rem  screen as it finds it.

rem  The installer puts Python straight into .venv; setup.bat makes a
rem  virtual environment with it under .venv\Scripts. Either is fine.
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=.venv\python.exe"
if not exist "%PY%" (
    echo Run setup.bat first - there is no environment here yet.
    pause
    exit /b 1
)

"%PY%" "%CD%\tools\time_read.py"
exit /b 0
