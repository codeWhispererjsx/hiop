@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-user.ps1"
if errorlevel 1 (
  echo.
  echo Agent removal did not complete. Review the error above and try again.
)
pause
