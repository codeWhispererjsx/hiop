$ErrorActionPreference="Stop"
$root=Join-Path $env:ProgramFiles "HIOP Agent"
if(Get-Service HIOPLocalAgent -ErrorAction SilentlyContinue){Stop-Service HIOPLocalAgent -Force;Push-Location $root;& (Join-Path $root ".venv\Scripts\python.exe") -m hiop_agent.windows_service remove;Pop-Location}
Write-Host "HIOP Local Agent service removed. Historical server observations were retained."
