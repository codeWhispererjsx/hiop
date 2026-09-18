$ErrorActionPreference = "Stop"

$desktopRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $desktopRoot "..")
$backendRoot = Join-Path $repoRoot "backend"
$runtimeRoot = Join-Path $desktopRoot "build-runtime"
$venvRoot = Join-Path $runtimeRoot "python"
$stampFile = Join-Path $runtimeRoot "requirements.sha256"
$requirementsFile = Join-Path $backendRoot "requirements.txt"
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
  $stream = [System.IO.File]::OpenRead($requirementsFile)
  try { $requirementsHash = [BitConverter]::ToString($sha256.ComputeHash($stream)).Replace("-", "") }
  finally { $stream.Dispose() }
}
finally { $sha256.Dispose() }
$python = $env:HIOP_BUILD_PYTHON
if (-not $python) { $python = "py" }

if ((Test-Path (Join-Path $venvRoot "Scripts\python.exe")) -and (Test-Path $stampFile)) {
  $existingHash = Get-Content $stampFile -Raw
  if ($existingHash.Trim() -eq $requirementsHash) {
    Write-Host "Backend Python runtime is already current at $venvRoot"
    exit 0
  }
}

if (Test-Path $venvRoot) {
  Remove-Item -LiteralPath $venvRoot -Recurse -Force
}
New-Item -ItemType Directory -Force $runtimeRoot | Out-Null

Write-Host "Creating HIOP backend Python runtime..."
& $python -3.12 -m venv $venvRoot
if ($LASTEXITCODE -ne 0) { throw "Unable to create Python runtime. Install Python 3.12 or set HIOP_BUILD_PYTHON." }

$venvPython = Join-Path $venvRoot "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Unable to upgrade pip in backend runtime." }

& $venvPython -m pip install -r $requirementsFile
if ($LASTEXITCODE -ne 0) { throw "Unable to install backend dependencies." }

Set-Content -Path $stampFile -Value $requirementsHash
Write-Host "Backend Python runtime ready at $venvRoot"

