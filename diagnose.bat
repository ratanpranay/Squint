@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Squint - diagnose
cd /d "%~dp0"
set "ROOT=%CD%"
rem  The installer puts Python straight into .venv; setup.bat makes a
rem  virtual environment with it under .venv\Scripts. Either is fine.
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%ROOT%\.venv\python.exe"
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%ROOT%\.venv\pythonw.exe"
set "OUT=%ROOT%\diagnose.txt"

rem ---------------------------------------------------------------
rem  Collects everything needed to work out what is wrong, into
rem  diagnose.txt. Reads only - changes nothing.
rem ---------------------------------------------------------------

echo Collecting information ...
> "%OUT%" echo Squint diagnostics
>>"%OUT%" echo Generated: %DATE% %TIME%
>>"%OUT%" echo Folder   : %ROOT%
>>"%OUT%" echo.

>>"%OUT%" echo === Windows ===
for /f "tokens=*" %%A in ('ver') do >>"%OUT%" echo %%A
>>"%OUT%" echo.

>>"%OUT%" echo === Install ===
if exist "%PYW%" (
    >>"%OUT%" echo environment: PRESENT ^(runs from source^)
) else (
    >>"%OUT%" echo environment: MISSING - setup.bat has not run
)
for %%F in ("%ROOT%\app\main.py" "%ROOT%\app\ui_main.py" "%ROOT%\app\ocr.py") do (
    if exist %%F for %%G in (%%F) do >>"%OUT%" echo %%~tG  %%~nxG
)
>>"%OUT%" echo.

>>"%OUT%" echo === OCR engine ===
if exist "%ROOT%\vendor\tesseract\tesseract.exe" (
    >>"%OUT%" echo vendor copy: PRESENT
    "%ROOT%\vendor\tesseract\tesseract.exe" --version >>"%OUT%" 2>&1
) else (
    >>"%OUT%" echo vendor copy: MISSING
)
if exist "%ROOT%\build\tesseract\tesseract.exe" >>"%OUT%" echo legacy build copy: PRESENT
where tesseract >>"%OUT%" 2>&1
>>"%OUT%" echo.

>>"%OUT%" echo === Windows text recognition ===
rem  Which languages this PC can actually read. Windows recognises only the
rem  languages it has packs for, and pointed at any other one it returns
rem  confident nonsense rather than an error - which is what made a Chinese
rem  page come back as "iRERJXIJXFL8Y". So the list matters.
if exist "%PY%" (
    "%PY%" -c "from app import ocr_windows as w; print('winsdk available:', w.AVAILABLE); print('can read:', ', '.join(w.available_languages()) or 'nothing')" >>"%OUT%" 2>&1
) else (
    >>"%OUT%" echo no .venv - setup.bat has not run
)
>>"%OUT%" echo.

>>"%OUT%" echo === Models ===
if exist "%APPDATA%\Squint\tessdata" (
    dir /b "%APPDATA%\Squint\tessdata" >>"%OUT%" 2>&1
) else (
    >>"%OUT%" echo no tessdata folder yet
)
>>"%OUT%" echo.

>>"%OUT%" echo === Settings ===
REM With the keys taken out. This file exists to be sent to somebody, and
REM it was printing live API keys in full. Whether a key is set is the
REM useful fact; the key itself never is.
if exist "%APPDATA%\Squint\config.json" (
    powershell -NoProfile -Command ^
      "(Get-Content -Raw '%APPDATA%\Squint\config.json') -replace '(\"[a-z_]*(api_key|token|secret)\"\s*:\s*\")[^\"]+\"', '$1set, hidden\"'" ^
      >>"%OUT%" 2>&1
) else (
    >>"%OUT%" echo no config.json yet
)
>>"%OUT%" echo.

>>"%OUT%" echo === Log ^(last 60 lines^) ===
if exist "%APPDATA%\Squint\squint.log" (
    powershell -NoProfile -Command ^
        "Get-Content -Tail 60 '%APPDATA%\Squint\squint.log'" >>"%OUT%" 2>&1
) else (
    >>"%OUT%" echo no log file yet
)
>>"%OUT%" echo.

>>"%OUT%" echo === Reaching Google ===
rem Which layer refuses, if one does. On a company network the answer is
rem usually TLS: a proxy that opens encrypted traffic presents its own
rem certificate, Windows trusts it so browsers work, and Python does not -
rem which is why a page can open in the browser while the app times out.
if exist "%PY%" (
    "%PY%" -c "from app import netcheck;print(netcheck.summary()[1])" >>"%OUT%" 2>&1
) else (
    >>"%OUT%" echo skipped - no .venv
)
>>"%OUT%" echo.

>>"%OUT%" echo === Build environment ===
if exist "%PY%" (
    "%PY%" -c "import sys;print('venv python', sys.version)" >>"%OUT%" 2>&1
    "%PY%" -m pip list >>"%OUT%" 2>&1
) else (
    >>"%OUT%" echo no .venv - build.bat has not run in this folder
)

echo.
echo  ===============================================
echo    Written to:
echo      %OUT%
echo    Send that file back. Nothing was changed.
echo  ===============================================
echo.
start "" notepad "%OUT%"
pause
exit /b 0
