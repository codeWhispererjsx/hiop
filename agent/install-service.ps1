param([Parameter(Mandatory=$true)][string]$BackendUrl,[Parameter(Mandatory=$true)][string]$EnrollmentToken)
$ErrorActionPreference="Stop"
$root=Join-Path $env:ProgramFiles "HIOP Agent";$data=Join-Path $env:ProgramData "HIOP Agent"
New-Item -ItemType Directory -Force -Path $root,$data | Out-Null
Copy-Item -Recurse -Force (Join-Path $PSScriptRoot "hiop_agent") $root
Copy-Item -Force (Join-Path $PSScriptRoot "requirements.txt") $root
py -3 -m venv (Join-Path $root ".venv")
& (Join-Path $root ".venv\Scripts\pip.exe") install -r (Join-Path $root "requirements.txt")
@{backend_url=$BackendUrl;data_dir=$data;heartbeat_seconds=60;poll_seconds=15;queue_max_items=10000;queue_retention_days=7;request_timeout_seconds=30;allow_insecure_http=$false}|ConvertTo-Json|Set-Content -Encoding UTF8 (Join-Path $data "agent.json")
$env:HIOP_AGENT_CONFIG=Join-Path $data "agent.json"
Push-Location $root
& (Join-Path $root ".venv\Scripts\python.exe") -m hiop_agent.runner --config $env:HIOP_AGENT_CONFIG --enroll $EnrollmentToken
& (Join-Path $root ".venv\Scripts\python.exe") -m hiop_agent.windows_service --startup auto install
Pop-Location
sc.exe failure HIOPLocalAgent reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
Start-Service HIOPLocalAgent
Write-Host "HIOP Local Agent installed and started."
