!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef OUTPUT_FILE
  !error "OUTPUT_FILE is required"
!endif
!ifndef BOOTSTRAP_SCRIPT
  !error "BOOTSTRAP_SCRIPT is required"
!endif
!ifndef PRODUCT_VERSION
  !error "PRODUCT_VERSION is required"
!endif

Name "HIOP Agent for Windows"
OutFile "${OUTPUT_FILE}"
Unicode True
RequestExecutionLevel user
VIProductVersion "${PRODUCT_VERSION}.0"
VIAddVersionKey "ProductName" "HIOP Agent for Windows"
VIAddVersionKey "FileDescription" "HIOP Agent installer"
VIAddVersionKey "FileVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Section "Install HIOP Agent"
  SetOutPath "$PLUGINSDIR"
  File /oname=install-agent.ps1 "${BOOTSTRAP_SCRIPT}"
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\install-agent.ps1"' $0
  ${If} $0 != 0
    Abort "HIOP Agent installation did not complete successfully."
  ${EndIf}
SectionEnd
