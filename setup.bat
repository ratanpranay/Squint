@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Squint - setup
cd /d "%~dp0"
set "ROOT=%CD%"
set "PYID=Python.Python.3.12"
set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python312"
set "VENV=%ROOT%\.venv"

rem ---------------------------------------------------------------
rem  Sets Squint up to run directly from source.
rem
rem  There is deliberately no compile step. Packaging into an .exe
rem  meant every fix needed a rebuild, and a rebuild that silently
rem  did not happen looked exactly like a fix that did not work.
rem  Running from source removes that whole class of problem: what
rem  you extract is what runs.
rem ---------------------------------------------------------------

echo.
echo  ===============================================
echo    Squint  -  setup
echo  ===============================================
echo.

rem  A copy put here by the Squint installer carries its own Python in
rem  .venv, with its packages already installed. Making a virtual
rem  environment over the top of it would break both.
if exist "%VENV%\pythonw.exe" if not exist "%VENV%\Scripts\pythonw.exe" (
    echo  This copy was installed by the Squint installer, with its own
    echo  Python and packages. Checking only the OCR engine ...
    echo.
    "%VENV%\python.exe" "%ROOT%\tools\fetch_deps.py"
    echo.
    pause
    exit /b 0
)

rem ---- 0. how deep is this folder? -----------------------------------
rem  Windows still refuses paths past 260 characters, and pip builds very
rem  deep ones inside .venv. Installing into a folder several levels down
rem  in Documents died partway through with "the filename or extension is
rem  too long", leaving a half-built environment and an error that says
rem  nothing about the real cause. Better to say so before starting.
call :strlen ROOT PATHLEN
if !PATHLEN! gtr 70 (
    echo.
    echo  NOTE: this folder is !PATHLEN! characters deep.
    echo     %ROOT%
    echo.
    echo  Windows limits paths to 260 characters and the installer builds
    echo  long ones inside here. If setup fails partway through, move the
    echo  whole folder somewhere short - C:\Squint - and run it again.
    echo.
)

rem ---- 1. Python ----------------------------------------------------
set "PYEXE="
for %%P in ("py -3.12" "py -3" "python") do (
    if not defined PYEXE (
        cmd /c %%~P -c "import sys,tkinter;assert sys.version_info>=(3,9)" >nul 2>&1
        if !errorlevel! equ 0 set "PYEXE=%%~P"
    )
)
if not defined PYEXE (
    rem -----------------------------------------------------------
    rem  Python is installed through winget, not downloaded here.
    rem
    rem  Installing it matters: on two test machines this was the
    rem  step people gave up at. But the obvious way to do it -
    rem  fetch python.exe into %TEMP% with a PowerShell policy
    rem  override and run it /quiet - is the exact shape of a
    rem  malware dropper, and Windows Defender blocked the whole
    rem  download on sight. The zip never reached the user at all.
    rem
    rem  winget is Microsoft's own package manager, shipped with
    rem  Windows. It downloads and installs Python itself, so no
    rem  script here fetches or executes anything, and there is no
    rem  heuristic to trip. Same result, nothing to flag.
    rem -----------------------------------------------------------
    echo  [1/4] Python is not installed yet.
    where winget >nul 2>&1
    if !errorlevel! equ 0 call :winget_python
)
if not defined PYEXE (
    echo.
    echo        Could not install it automatically.
    echo        Opening the download page. Install Python, and be sure
    echo        to tick "Add python.exe to PATH" on the first screen.
    echo        Then run setup.bat again.
    echo.
    start "" "https://www.python.org/downloads/windows/"
    goto :fail
) else (
    echo  [1/4] Python: %PYEXE%
)

rem ---- 2. environment + packages ------------------------------------
echo  [2/4] Installing packages ...
if not exist "%VENV%\Scripts\pythonw.exe" (
    cmd /c %PYEXE% -m venv "%VENV%"
    if !errorlevel! neq 0 (echo        could not create the environment & goto :fail)
)
set "VPY=%VENV%\Scripts\python.exe"
set "VPYW=%VENV%\Scripts\pythonw.exe"
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VPY%" -m pip install --quiet --disable-pip-version-check -r "%ROOT%\requirements.txt"
if !errorlevel! neq 0 (echo        package install failed - check your connection & goto :fail)

rem ---- 3. OCR engine ------------------------------------------------
echo  [3/4] Checking the OCR engine ...
"%VPY%" "%ROOT%\tools\fetch_deps.py"
if !errorlevel! neq 0 (
    echo.
    echo        The OCR engine is not ready. Screen translation will not
    echo        work until it is. See the messages above.
    echo.
    choice /c YN /n /m "        Continue anyway? [Y/N] "
    if !errorlevel! equ 2 goto :fail
)

rem ---- 4. shortcut ---------------------------------------------------
echo  [4/4] Creating a Desktop shortcut ...
powershell -NoProfile -Command ^
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" ^
    "[Environment]::GetFolderPath('Desktop')+'\Squint.lnk');" ^
    "$s.TargetPath='%VPYW%';" ^
    "$s.Arguments='\"%ROOT%\run_app.py\"';" ^
    "$s.WorkingDirectory='%ROOT%';" ^
    "$s.IconLocation='%ROOT%\assets\icon.ico';$s.Save()" >nul 2>&1
if exist "%USERPROFILE%\Desktop\Squint.lnk" (echo        created.) else (echo        see Squint.bat in this folder.)

echo.
echo  ===============================================
echo    Ready.
echo.
echo    Start it from the Desktop shortcut, or by
echo    double-clicking Squint.bat here.
echo.
echo    Then press CTRL+ALT+X anywhere to translate.
echo  ===============================================
echo.
choice /c YN /n /m "  Start Squint now? [Y/N] "
if !errorlevel! equ 1 start "" "%VPYW%" "%ROOT%\run_app.py"
echo.
pause
exit /b 0

rem  Install Python with winget, then find it without reopening the window.
rem  A subroutine, not an inline block: a multi-line command inside an
rem  if(...) block needs caret continuations, and one stray character in
rem  those turns the whole thing into a silent no-op.
:winget_python
echo        Installing it with winget. This takes a minute.
echo.
winget install -e --id %PYID% --source winget --scope user --accept-package-agreements --accept-source-agreements
if !errorlevel! neq 0 winget install -e --id %PYID% --source winget --accept-package-agreements --accept-source-agreements
echo.
rem  PATH is read once, when the console window opens, so a Python that
rem  was installed thirty seconds ago is not on it. Putting the install
rem  directory on this session's PATH is what makes the probe below find
rem  it - the alternative is telling the user to close the window and
rem  start again, which is where people give up.
if exist "%PYDIR%\python.exe" set "PATH=%PYDIR%;%PYDIR%\Scripts;%PATH%"
for %%P in ("py -3.12" "py -3" "python") do (
    if not defined PYEXE (
        cmd /c %%~P -c "import sys,tkinter;assert sys.version_info>=(3,9)" >nul 2>&1
        if !errorlevel! equ 0 set "PYEXE=%%~P"
    )
)
goto :eof

:fail
echo.
pause
exit /b 1

rem  Batch has no way to measure a string, so this halves it repeatedly.
:strlen
setlocal EnableDelayedExpansion
set "s=!%~1!#"
set "len=0"
for %%A in (4096 2048 1024 512 256 128 64 32 16 8 4 2 1) do (
    if "!s:~%%A!" neq "" (
        set /a len+=%%A
        set "s=!s:~%%A!"
    )
)
endlocal & set "%~2=%len%"
goto :eof
