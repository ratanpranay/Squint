@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Squint - build

rem ---------------------------------------------------------------
rem  Builds Squint.exe. Double-click and wait.
rem  Optional:  build.bat onefile   -> one big .exe (slower to start)
rem ---------------------------------------------------------------

cd /d "%~dp0"
set "ROOT=%CD%"
set "PYVER=3.12.7"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"
set "VENV=%ROOT%\.venv"

echo.
echo  ===============================================
echo    Squint  -  build
echo  ===============================================
echo.

rem ---- 1. find a usable Python ------------------------------------
set "PYEXE="
for %%P in ("py -3.12" "py -3" "python") do (
    if not defined PYEXE (
    rem  No auto-download of Python here either - same dropper pattern,
    rem  same Defender block. See the note in setup.bat.
    echo  Python is not installed. Get it from
    echo      https://www.python.org/downloads/windows/
    echo  and tick "Add python.exe to PATH", then run build.bat again.
    goto :fail
) else (
    echo  [1/5] Using Python: %PYEXE%
)

rem ---- 2. virtual environment -------------------------------------
echo  [2/5] Preparing the build environment ...
if not exist "%VENV%\Scripts\python.exe" (
    cmd /c %PYEXE% -m venv "%VENV%"
    if !errorlevel! neq 0 (
        echo  Could not create the virtual environment.
        goto :fail
    )
)
set "VPY=%VENV%\Scripts\python.exe"

rem ---- 3. dependencies --------------------------------------------
echo  [3/5] Installing dependencies ...
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VPY%" -m pip install --quiet --disable-pip-version-check -r "%ROOT%\requirements.txt"
if !errorlevel! neq 0 (
    echo  Dependency install failed. Check your internet connection.
    goto :fail
)
"%VPY%" -m pip install --quiet --disable-pip-version-check pyinstaller
if !errorlevel! neq 0 (
    echo  Could not install PyInstaller.
    goto :fail
)

rem ---- 4. OCR engine + language packs -----------------------------
echo  [4/5] Fetching the OCR engine and language models ...
"%VPY%" "%ROOT%\tools\fetch_deps.py"
set "DEPS=!errorlevel!"
if !DEPS! neq 0 (
    echo.
    echo  ***********************************************
    echo    WARNING: the OCR engine is NOT ready.
    echo    The app will build, but screen translation will
    echo    not work until you run fix_ocr.bat.
    echo  ***********************************************
    echo.
    choice /c YN /n /m "  Continue building anyway? [Y/N] "
    if !errorlevel! equ 2 goto :fail
)

rem ---- 4b. quick sanity check on the tray menu ---------------------
"%VPY%" "%ROOT%\tools\smoke_tray.py" >"%TEMP%\snaptray.log" 2>&1
if !errorlevel! neq 0 (
    echo        note: tray self-check failed, see %TEMP%\snaptray.log
    echo              the app will still run, just without a tray icon.
)

rem ---- 5. build ----------------------------------------------------
echo  [5/5] Building Squint.exe ^(this takes a few minutes^) ...
set "SNAP_ONEFILE="
if /i "%~1"=="onefile" set "SNAP_ONEFILE=1"
if exist "%ROOT%\dist\Squint" rmdir /s /q "%ROOT%\dist\Squint" >nul 2>&1
"%VPY%" -m PyInstaller --noconfirm --clean "%ROOT%\Squint.spec"
if !errorlevel! neq 0 (
    echo  The build failed. Scroll up for the first line that says "ERROR".
    goto :fail
)

set "OUT=%ROOT%\dist\Squint\Squint.exe"
if /i "%SNAP_ONEFILE%"=="1" set "OUT=%ROOT%\dist\Squint.exe"
if not exist "%OUT%" (
    echo  Build finished but the .exe is missing.
    goto :fail
)

rem `for /r ... in (name)` without a wildcard does NOT check existence -
rem cmd emits that name for every directory it walks. dir /s /b does.
set "BUNDLED="
for /f "delims=" %%F in ('dir /s /b "%ROOT%\dist\tesseract.exe" 2^>nul') do (
    if not defined BUNDLED set "BUNDLED=%%F"
)

echo.
echo  ===============================================
echo    Done.
echo    %OUT%
if defined BUNDLED (
    echo    OCR engine bundled: OK
) else (
    echo    OCR engine bundled: MISSING - run fix_ocr.bat
)
echo  ===============================================
echo.

choice /c YN /n /m "  Create a Desktop shortcut? [Y/N] "
if !errorlevel! equ 1 (
    powershell -NoProfile -Command ^
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" ^
        "[Environment]::GetFolderPath('Desktop')+'\Squint.lnk');" ^
        "$s.TargetPath='%OUT%';$s.WorkingDirectory=Split-Path '%OUT%';" ^
        "$s.IconLocation='%OUT%';$s.Save()"
    echo  Shortcut created.
)

echo.
choice /c YN /n /m "  Start Squint now? [Y/N] "
if !errorlevel! equ 1 start "" "%OUT%"
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
