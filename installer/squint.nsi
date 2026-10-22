; Squint-Setup-<version>.exe — built by tools/make_installer.py, which
; passes VERSION, STAGE (the folder to install) and OUTFILE.
;
; Per-user install into %LOCALAPPDATA%\Programs\Squint: no admin prompt,
; and the folder stays writable, which is what lets the in-app updater
; replace the code later without ever needing a new installer.

Unicode true
SetCompressor /SOLID lzma

!ifndef VERSION
  !define VERSION "0.0.0"
!endif

Name "Squint ${VERSION}"
OutFile "${OUTFILE}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\Squint"
BrandingText "Squint ${VERSION}"

!include "MUI2.nsh"
!define MUI_ICON "${STAGE}/assets/icon.ico"
!define MUI_UNICON "${STAGE}/assets/icon.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\.venv\pythonw.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS '"$INSTDIR\run_app.py"'
!define MUI_FINISHPAGE_RUN_TEXT "Start Squint"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\Squint"

Section "Squint"
  SetOutPath "$INSTDIR"
  File /r "${STAGE}/*"

  CreateShortCut "$SMPROGRAMS\Squint.lnk" "$INSTDIR\.venv\pythonw.exe" \
    '"$INSTDIR\run_app.py"' "$INSTDIR\assets\icon.ico" 0
  CreateShortCut "$DESKTOP\Squint.lnk" "$INSTDIR\.venv\pythonw.exe" \
    '"$INSTDIR\run_app.py"' "$INSTDIR\assets\icon.ico" 0

  WriteUninstaller "$INSTDIR\Uninstall Squint.exe"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "Squint"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "Publisher" "Squint"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\assets\icon.ico"
  WriteRegStr HKCU "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\Uninstall Squint.exe"'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\Squint.lnk"
  Delete "$DESKTOP\Squint.lnk"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Squint"
  DeleteRegKey HKCU "${UNINST}"
  ; Settings, keys and downloaded languages live in the data folder, not
  ; here, and are left for a reinstall.
  RMDir /r "$INSTDIR"
SectionEnd
