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
$postgresStartedByHIOP = $false
$postgresProcess = $null
$postgresData = Join-Path $desktopData "postgres-data"
$postgresPort = if ($env:HIOP_DESKTOP_POSTGRES_PORT) { [int]$env:HIOP_DESKTOP_POSTGRES_PORT } else { 55432 }
$postgresPassword = if ($env:HIOP_DESKTOP_POSTGRES_PASSWORD) { $env:HIOP_DESKTOP_POSTGRES_PASSWORD } else { "hiop_desktop_local_password" }
$postgresDatabase = if ($env:HIOP_DESKTOP_POSTGRES_DATABASE) { $env:HIOP_DESKTOP_POSTGRES_DATABASE } else { "hiop_desktop" }
$postgresUser = if ($env:HIOP_DESKTOP_POSTGRES_USER) { $env:HIOP_DESKTOP_POSTGRES_USER } else { "postgres" }
$packagedPostgres = Join-Path $resourceRoot "postgres"
$repoPostgres = Join-Path (Resolve-Path (Join-Path $scriptRoot "..\..")) "desktop\build-runtime\postgres"
$postgresRoot = if (Test-Path (Join-Path $packagedPostgres "bin\pg_ctl.exe")) { $packagedPostgres } elseif (Test-Path (Join-Path $repoPostgres "bin\pg_ctl.exe")) { $repoPostgres } else { "" }
$python = $env:HIOP_DESKTOP_PYTHON
$packagedPython = Join-Path $resourceRoot "python\Scripts\python.exe"
$repoPython = Join-Path (Resolve-Path (Join-Path $scriptRoot "..\..")) "backend\.venv\Scripts\python.exe"
if (-not $python -and (Test-Path $packagedPython)) { $python = $packagedPython }
if (-not $python -and (Test-Path $repoPython)) { $python = $repoPython }
if (-not $python) { $python = "py" }

function Write-HIOPLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  # A running API process can temporarily retain the shared log. Logging must
  # never prevent the launcher from discovering and reusing that API.
  try { Add-Content -Path $logFile -Value $line -ErrorAction Stop } catch { }
}

function Invoke-HIOPProcess([string]$FilePath, [string[]]$Arguments, [string]$FailureMessage, [hashtable]$ExtraEnvironment = @{}) {
  $previousValues = @{}
  foreach ($key in $ExtraEnvironment.Keys) {
    $previousValues[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
    [Environment]::SetEnvironmentVariable($key, [string]$ExtraEnvironment[$key], "Process")
  }
  try {
    & $FilePath @Arguments *>> $logFile
    if ($LASTEXITCODE -ne 0) { throw "$FailureMessage Exit code: $LASTEXITCODE. Check $logFile" }
  }
  finally {
    foreach ($key in $ExtraEnvironment.Keys) {
      [Environment]::SetEnvironmentVariable($key, $previousValues[$key], "Process")
    }
  }
}

function Start-HIOPPostgres {
  if ($env:HIOP_DESKTOP_DATABASE_URL) {
    $env:DATABASE_URL = $env:HIOP_DESKTOP_DATABASE_URL
    Write-HIOPLog "Using the HIOP Desktop database override"
    return
  }
  # Do not inherit a developer or hosted database setting from Windows.
  Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
  if (-not $postgresRoot) {
    throw "Bundled PostgreSQL runtime was not found. Rebuild the desktop app with npm --prefix desktop run build:postgres-runtime."
  }

  $bin = Join-Path $postgresRoot "bin"
  $pgCtl = Join-Path $bin "pg_ctl.exe"
  $initDb = Join-Path $bin "initdb.exe"
  $psql = Join-Path $bin "psql.exe"
  $pgIsReady = Join-Path $bin "pg_isready.exe"
  $serverLog = Join-Path $logRoot "postgres.log"
  $serverErrorLog = Join-Path $logRoot "postgres-error.log"
  New-Item -ItemType Directory -Force $desktopData | Out-Null

  if (-not (Test-Path (Join-Path $postgresData "PG_VERSION"))) {
    Write-HIOPLog "Initializing local PostgreSQL data directory at $postgresData"
    New-Item -ItemType Directory -Force $postgresData | Out-Null
    $pwFile = Join-Path $desktopData "postgres-password.txt"
    Set-Content -LiteralPath $pwFile -Value $postgresPassword -NoNewline
    try {
      Invoke-HIOPProcess $initDb @("-D", $postgresData, "-U", $postgresUser, "-A", "scram-sha-256", "--pwfile", $pwFile, "-E", "UTF8") "PostgreSQL initialization failed."
    }
    finally {
      if (Test-Path $pwFile) { Remove-Item -LiteralPath $pwFile -Force }
    }
  }

  $env:PGPASSWORD = $postgresPassword
  $env:PGCONNECT_TIMEOUT = "5"
  $ready = $false
  & $pgIsReady "-h" "127.0.0.1" "-p" "$postgresPort" "-U" $postgresUser *> $null
  if ($LASTEXITCODE -eq 0) { $ready = $true }

  if (-not $ready) {
    Write-HIOPLog "Starting bundled PostgreSQL on 127.0.0.1:$postgresPort"
        $postgresExe = Join-Path $bin "postgres.exe"
    $script:postgresProcess = Start-Process -FilePath $postgresExe -ArgumentList @("-D", "`"$postgresData`"", "-h", "127.0.0.1", "-p", "$postgresPort") -WindowStyle Hidden -PassThru -RedirectStandardOutput $serverLog -RedirectStandardError $serverErrorLog
    $readyAfterStart = $false
    # A database that is recovering after an unexpected Windows shutdown can
    # need longer than the normal startup time. Keep the setup screen waiting
    # instead of giving up while PostgreSQL is still doing its safety checks.
    for ($attempt = 0; $attempt -lt 240; $attempt++) {
      Start-Sleep -Milliseconds 500
      & $pgIsReady "-h" "127.0.0.1" "-p" "$postgresPort" "-U" $postgresUser *> $null
      if ($LASTEXITCODE -eq 0) { $readyAfterStart = $true; break }
      if ($script:postgresProcess.HasExited) { break }
    }
    if (-not $readyAfterStart) { throw "PostgreSQL failed to become ready. Check $serverLog" }
    $script:postgresStartedByHIOP = $true
  }
  else {
    Write-HIOPLog "PostgreSQL is already accepting connections on 127.0.0.1:$postgresPort"
  }

  Write-HIOPLog "Ensuring HIOP desktop database exists"
  $existsSql = "SELECT 1 FROM pg_database WHERE datname = '$postgresDatabase';"
  $exists = & $psql "-w" "-h" "127.0.0.1" "-p" "$postgresPort" "-U" $postgresUser "-d" "postgres" "-tAc" $existsSql 2>> $logFile
  if ($LASTEXITCODE -ne 0) { throw "Unable to check HIOP desktop database. Check $logFile" }
  if (($exists -join "").Trim() -ne "1") {
    Invoke-HIOPProcess $psql @("-w", "-h", "127.0.0.1", "-p", "$postgresPort", "-U", $postgresUser, "-d", "postgres", "-c", "CREATE DATABASE $postgresDatabase;") "Unable to create HIOP desktop database." @{ "PGPASSWORD" = $postgresPassword; "PGCONNECT_TIMEOUT" = "5" }
  }

  $env:DATABASE_URL = "postgresql+psycopg2://$postgresUser`:$postgresPassword@127.0.0.1:$postgresPort/$postgresDatabase"
}

function Stop-HIOPPostgres {
  if (-not $postgresStartedByHIOP) { return }
  if (-not $postgresRoot) { return }
  $pgCtl = Join-Path $postgresRoot "bin\pg_ctl.exe"
  if (Test-Path $pgCtl) {
    Write-HIOPLog "Stopping bundled PostgreSQL"
    & $pgCtl "-D" $postgresData "-m" "fast" "-w" "stop" *>> $logFile
  }
}

Write-HIOPLog "Starting HIOP Desktop backend on 127.0.0.1:$Port"
Write-HIOPLog "Backend root: $backendRoot"
Write-HIOPLog "Python runtime: $python"
Write-HIOPLog "PostgreSQL runtime: $postgresRoot"

# The desktop app may be reopened while its private service is already
# running. Reusing that healthy service is correct; starting a second API on
# the same port is not. This avoids a false "backend did not start" popup.
try {
  $existingHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
  if ($existingHealth.status -eq "healthy") {
    Write-HIOPLog "A healthy HIOP Desktop backend is already running; reusing it."
    exit 0
  }
}
catch {
  # No healthy local API is running yet, so continue with normal startup.
}

if (-not $env:APP_NAME) { $env:APP_NAME = "HIOP Desktop" }
if (-not $env:APP_VERSION) { $env:APP_VERSION = "desktop-dev" }
if (-not $env:DEBUG) { $env:DEBUG = "true" }
if (-not $env:ENVIRONMENT) { $env:ENVIRONMENT = "development" }
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "desktop-local-development-secret-change-before-release" }
if (-not $env:CORS_ORIGINS) { $env:CORS_ORIGINS = '["http://127.0.0.1:5173","http://localhost:5173"]' }
if (-not $env:DISCOVERY_EXECUTION_MODE) { $env:DISCOVERY_EXECUTION_MODE = "backend" }
if (-not $env:SCHEDULER_ENABLED) { $env:SCHEDULER_ENABLED = "true" }
if (-not $env:HIOP_AD_SECRET_KEY) { $env:HIOP_AD_SECRET_KEY = "desktop-local-ad-secret-change-before-release" }
if (-not $env:HIOP_SNMP_SECRET_KEY) { $env:HIOP_SNMP_SECRET_KEY = "desktop-local-snmp-secret-change-release" }
if (-not $env:HIOP_DISCOVERY_CREDENTIAL_KEY) { $env:HIOP_DISCOVERY_CREDENTIAL_KEY = "desktop-local-discovery-secret-change" }
if ($postgresRoot) {
  if (-not $env:PG_DUMP_PATH) { $env:PG_DUMP_PATH = Join-Path $postgresRoot "bin\pg_dump.exe" }
  if (-not $env:PG_RESTORE_PATH) { $env:PG_RESTORE_PATH = Join-Path $postgresRoot "bin\pg_restore.exe" }
  if (-not $env:BACKUP_DIR) { $env:BACKUP_DIR = Join-Path $desktopData "backups" }
}


Push-Location $backendRoot
try {
  Start-HIOPPostgres

  Write-HIOPLog "Applying database migrations"
  # Alembic writes normal progress messages to stderr. With this script's
  # strict PowerShell error policy, PowerShell can mistake those messages for
  # a failed command even when Alembic returns success. Keep the native
  # command output in the log and decide success solely from its exit code.
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $python -m alembic upgrade head *>> $logFile
  $migrationExitCode = $LASTEXITCODE
  $ErrorActionPreference = $previousErrorActionPreference
  if ($migrationExitCode -ne 0) { throw "Database migration failed. Check $logFile" }

  Write-HIOPLog "Launching API process"
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port *>> $logFile
  $apiExitCode = $LASTEXITCODE
  $ErrorActionPreference = $previousErrorActionPreference
  if ($apiExitCode -ne 0) { throw "API process exited with code $apiExitCode. Check $logFile" }
}
catch {
  Write-HIOPLog "ERROR: $($_.Exception.Message)"
  throw
}
finally {
  Pop-Location
  Stop-HIOPPostgres
}

