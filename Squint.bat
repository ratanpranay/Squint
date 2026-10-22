@echo off
cd /d "%~dp0"
rem  The installer puts Python straight into .venv; setup.bat makes a
rem  virtual environment with it under .venv\Scripts. Either is fine.
set "PYW=.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=.venv\pythonw.exe"
if not exist "%PYW%" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
start "" "%PYW%" "%CD%\run_app.py"
exit /b 0
