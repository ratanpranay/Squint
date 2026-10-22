@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Squint - uninstall
cd /d "%~dp0"

rem ---------------------------------------------------------------
rem  Removes Squint. Asks before each step; nothing is
rem  deleted unless you say Y.
rem ---------------------------------------------------------------

echo.
echo  ===============================================
echo    Squint  -  uninstall
echo  ===============================================
echo.
echo  This folder: %CD%
echo.

rem ---- 1. stop the app ---------------------------------------------
echo  [1/5] Closing Squint if it is running ...
taskkill /f /im Squint.exe /t >nul 2>&1
taskkill /f /im pythonw.exe /t >nul 2>&1
if !errorlevel! equ 0 (echo        closed.) else (echo        not running.)

rem ---- 2. desktop shortcut -----------------------------------------
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command ^
    "[Environment]::GetFolderPath('Desktop')" 2^>nul`) do set "DESKTOP=%%D"
if not defined DESKTOP set "DESKTOP=%USERPROFILE%\Desktop"
if exist "%DESKTOP%\Squint.lnk" (
    del /q "%DESKTOP%\Squint.lnk" >nul 2>&1
    echo  [2/5] Desktop shortcut removed.
) else (
    echo  [2/5] No desktop shortcut found.
)

rem ---- 3. start-with-Windows entry ---------------------------------
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Squint >nul 2>&1
if !errorlevel! equ 0 (
    reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Squint /f >nul 2>&1
    echo  [3/5] Startup entry removed.
) else (
    echo  [3/5] No startup entry found.
)

rem ---- 4. settings and OCR models ----------------------------------
echo.
if exist "%APPDATA%\Squint" (
    echo  [4/5] Settings and downloaded OCR models live in:
    echo            %APPDATA%\Squint
    echo        Keep them if you might reinstall - they are ~50 MB and
    echo        save re-downloading the language models.
    choice /c YN /n /m "        Delete them? [Y/N] "
    if !errorlevel! equ 1 (
        rmdir /s /q "%APPDATA%\Squint" >nul 2>&1
        echo        deleted.
    ) else (
        echo        kept.
    )
) else (
    echo  [4/5] No settings folder found.
)
if exist "%TEMP%\squint_tesseract" (
    rmdir /s /q "%TEMP%\squint_tesseract" >nul 2>&1
)
del /q "%TEMP%\snaptray.log" >nul 2>&1

rem ---- 5. build output ---------------------------------------------
echo.
echo  [5/5] The environment and OCR engine in this folder
echo        ^(.venv, vendor, build, dist^) are about 700 MB. Removing
echo        them keeps the source but means setup.bat has to
echo        download everything again.
choice /c YN /n /m "        Delete build output? [Y/N] "
if !errorlevel! equ 1 (
    if exist ".venv"  rmdir /s /q ".venv"  >nul 2>&1
    if exist "vendor" rmdir /s /q "vendor" >nul 2>&1
    if exist "build"  rmdir /s /q "build"  >nul 2>&1
    if exist "dist"   rmdir /s /q "dist"   >nul 2>&1
    echo        deleted.
) else (
    echo        kept.
)

echo.
echo  ===============================================
echo    Done.
echo.
echo    A script cannot delete the folder it is running from,
echo    so to remove Squint completely, close this window
echo    and delete:
echo        %CD%
echo.
echo    Python was installed separately ^(if build.bat installed it
echo    at all^) and is left alone - remove it from Windows Settings
echo    ^> Apps if you do not want it.
echo  ===============================================
echo.
pause
exit /b 0
