param([int]$Port = 0)

$ErrorActionPreference = "Stop"
if ($Port -le 0) { if ($env:HIOP_DESKTOP_PORT) { $Port = [int]$env:HIOP_DESKTOP_PORT } else { $Port = 8765 } }

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$backendRoot = Join-Path $repoRoot "backend"
$python = $env:HIOP_DESKTOP_PYTHON
if (-not $python) { $python = "python" }

if (-not $env:APP_NAME) { $env:APP_NAME = "HIOP Desktop" }
if (-not $env:APP_VERSION) { $env:APP_VERSION = "desktop-dev" }
if (-not $env:DEBUG) { $env:DEBUG = "true" }
if (-not $env:ENVIRONMENT) { $env:ENVIRONMENT = "development" }
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "desktop-local-development-secret-change-before-release" }
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/hiop_desktop" }
if (-not $env:CORS_ORIGINS) { $env:CORS_ORIGINS = '[""http://127.0.0.1:5173"",""http://localhost:5173""]' }
if (-not $env:DISCOVERY_EXECUTION_MODE) { $env:DISCOVERY_EXECUTION_MODE = "backend" }
if (-not $env:SCHEDULER_ENABLED) { $env:SCHEDULER_ENABLED = "true" }
if (-not $env:HIOP_AD_SECRET_KEY) { $env:HIOP_AD_SECRET_KEY = "desktop-local-ad-secret-change-before-release" }
if (-not $env:HIOP_SNMP_SECRET_KEY) { $env:HIOP_SNMP_SECRET_KEY = "desktop-local-snmp-secret-change-release" }
if (-not $env:HIOP_DISCOVERY_CREDENTIAL_KEY) { $env:HIOP_DISCOVERY_CREDENTIAL_KEY = "desktop-local-discovery-secret-change" }

Push-Location $backendRoot
try {
  & $python -m alembic upgrade head
  & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
}
finally {
  Pop-Location
}



