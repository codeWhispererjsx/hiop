@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-user.ps1"
if errorlevel 1 (
  echo.
  echo Agent installation did not complete. Review the error above and try again.
)
pause
