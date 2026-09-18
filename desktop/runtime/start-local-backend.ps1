param([int]$Port = 0)

$ErrorActionPreference = "Stop"
if ($Port -le 0) {
  if ($env:HIOP_DESKTOP_PORT) { $Port = [int]$env:HIOP_DESKTOP_PORT } else { $Port = 8765 }
}

$scriptRoot = Resolve-Path $PSScriptRoot
$resourceRoot = if ($env:HIOP_DESKTOP_RESOURCES) { Resolve-Path $env:HIOP_DESKTOP_RESOURCES } else { Resolve-Path (Join-Path $scriptRoot "..\..") }
$packagedBackend = Join-Path $resourceRoot "backend"
$repoBackend = Join-Path (Resolve-Path (Join-Path $scriptRoot "..\..")) "backend"
$backendRoot = if (Test-Path $packagedBackend) { $packagedBackend } else { $repoBackend }
$desktopData = Join-Path $env:LOCALAPPDATA "HIOP Desktop"
$logRoot = Join-Path $desktopData "logs"
New-Item -ItemType Directory -Force $logRoot | Out-Null
$logFile = Join-Path $logRoot "backend.log"
$python = $env:HIOP_DESKTOP_PYTHON
$packagedPython = Join-Path $resourceRoot "python\Scripts\python.exe"
$repoPython = Join-Path (Resolve-Path (Join-Path $scriptRoot "..\..")) "backend\.venv\Scripts\python.exe"
if (-not $python -and (Test-Path $packagedPython)) { $python = $packagedPython }
if (-not $python -and (Test-Path $repoPython)) { $python = $repoPython }
if (-not $python) { $python = "py" }

function Write-HIOPLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $logFile -Value $line
}

Write-HIOPLog "Starting HIOP Desktop backend on 127.0.0.1:$Port"
Write-HIOPLog "Backend root: $backendRoot"
Write-HIOPLog "Python runtime: $python"

if (-not $env:APP_NAME) { $env:APP_NAME = "HIOP Desktop" }
if (-not $env:APP_VERSION) { $env:APP_VERSION = "desktop-dev" }
if (-not $env:DEBUG) { $env:DEBUG = "true" }
if (-not $env:ENVIRONMENT) { $env:ENVIRONMENT = "development" }
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "desktop-local-development-secret-change-before-release" }
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/hiop_desktop" }
if (-not $env:CORS_ORIGINS) { $env:CORS_ORIGINS = '["http://127.0.0.1:5173","http://localhost:5173"]' }
if (-not $env:DISCOVERY_EXECUTION_MODE) { $env:DISCOVERY_EXECUTION_MODE = "backend" }
if (-not $env:SCHEDULER_ENABLED) { $env:SCHEDULER_ENABLED = "true" }
if (-not $env:HIOP_AD_SECRET_KEY) { $env:HIOP_AD_SECRET_KEY = "desktop-local-ad-secret-change-before-release" }
if (-not $env:HIOP_SNMP_SECRET_KEY) { $env:HIOP_SNMP_SECRET_KEY = "desktop-local-snmp-secret-change-release" }
if (-not $env:HIOP_DISCOVERY_CREDENTIAL_KEY) { $env:HIOP_DISCOVERY_CREDENTIAL_KEY = "desktop-local-discovery-secret-change" }

Push-Location $backendRoot
try {
  Write-HIOPLog "Applying database migrations"
  & $python -m alembic upgrade head *>> $logFile
  if ($LASTEXITCODE -ne 0) { throw "Database migration failed. Check $logFile" }

  Write-HIOPLog "Launching API process"
  & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port *>> $logFile
  if ($LASTEXITCODE -ne 0) { throw "API process exited with code $LASTEXITCODE. Check $logFile" }
}
catch {
  Write-HIOPLog "ERROR: $($_.Exception.Message)"
  throw
}
finally {
  Pop-Location
}
