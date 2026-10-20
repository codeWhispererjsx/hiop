$ErrorActionPreference = "Stop"

$desktopRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $desktopRoot "..")
$backendRoot = Join-Path $repoRoot "backend"
$runtimeRoot = Join-Path $desktopRoot "build-runtime"
$pythonRuntimeRoot = Join-Path $runtimeRoot "python"
$stampFile = Join-Path $runtimeRoot "requirements.sha256"
$requirementsFile = Join-Path $backendRoot "requirements.txt"
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
  $stream = [System.IO.File]::OpenRead($requirementsFile)
  try { $requirementsHash = [BitConverter]::ToString($sha256.ComputeHash($stream)).Replace("-", "") }
  finally { $stream.Dispose() }
}
finally { $sha256.Dispose() }
$requirementsHash = "$requirementsHash|portable-python-1"
$buildPython = $env:HIOP_BUILD_PYTHON
$buildPythonArguments = @()
if (-not $buildPython) {
  $buildPython = "py"
  $buildPythonArguments = @("-3.12")
}

if ((Test-Path (Join-Path $pythonRuntimeRoot "python.exe")) -and (Test-Path $stampFile)) {
  $existingHash = Get-Content $stampFile -Raw
  if ($existingHash.Trim() -eq $requirementsHash) {
    Write-Host "Backend Python runtime is already current at $pythonRuntimeRoot"
    exit 0
  }
}

$pythonInfo = & $buildPython @buildPythonArguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'); print(sys.base_prefix)"
if ($LASTEXITCODE -ne 0) { throw "Unable to run the build Python interpreter. Install Python 3.12 or set HIOP_BUILD_PYTHON to its executable." }
$pythonInfo = @($pythonInfo)
if ($pythonInfo.Count -lt 2 -or $pythonInfo[0].Trim() -ne "3.12") {
  throw "The desktop backend runtime requires Python 3.12. Set HIOP_BUILD_PYTHON to a Python 3.12 executable."
}
$pythonBaseRoot = $pythonInfo[1].Trim()
$pythonBaseExecutable = Join-Path $pythonBaseRoot "python.exe"
if (-not (Test-Path $pythonBaseExecutable)) { throw "The Python base runtime was not found at $pythonBaseRoot." }

if (Test-Path $pythonRuntimeRoot) {
  Remove-Item -LiteralPath $pythonRuntimeRoot -Recurse -Force
}
New-Item -ItemType Directory -Force $runtimeRoot | Out-Null
New-Item -ItemType Directory -Force $pythonRuntimeRoot | Out-Null

Write-Host "Copying portable Python runtime from $pythonBaseRoot..."
foreach ($item in Get-ChildItem -LiteralPath $pythonBaseRoot -Force) {
  if ($item.PSIsContainer) {
    if ($item.Name -in @("Doc", "Include", "Scripts", "Tools", "libs", "tcl")) { continue }

    $destination = Join-Path $pythonRuntimeRoot $item.Name
    New-Item -ItemType Directory -Force $destination | Out-Null
    if ($item.Name -eq "Lib") {
      Get-ChildItem -LiteralPath $item.FullName -Force |
        Where-Object { $_.Name -ne "site-packages" } |
        Copy-Item -Destination $destination -Recurse -Force
    }
    else {
      Get-ChildItem -LiteralPath $item.FullName -Force |
        Copy-Item -Destination $destination -Recurse -Force
    }
  }
  else {
    Copy-Item -LiteralPath $item.FullName -Destination $pythonRuntimeRoot -Force
  }
}
$runtimePython = Join-Path $pythonRuntimeRoot "python.exe"
if (-not (Test-Path $runtimePython)) { throw "Unable to stage the Python executable in $pythonRuntimeRoot." }

$sitePackages = Join-Path $pythonRuntimeRoot "Lib\site-packages"
New-Item -ItemType Directory -Force $sitePackages | Out-Null

Write-Host "Installing backend dependencies into the portable runtime..."
& $buildPython @buildPythonArguments -m pip install --disable-pip-version-check --no-cache-dir --target $sitePackages -r $requirementsFile
if ($LASTEXITCODE -ne 0) { throw "Unable to install backend dependencies into the portable runtime." }

& $runtimePython -c "import alembic, fastapi, uvicorn"
if ($LASTEXITCODE -ne 0) { throw "The staged Python runtime failed its backend import check." }

Set-Content -Path $stampFile -Value $requirementsHash
Write-Host "Portable backend Python runtime ready at $pythonRuntimeRoot"
