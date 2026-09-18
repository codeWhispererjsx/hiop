$ErrorActionPreference = "Stop"

$desktopRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $desktopRoot "..")
$resourcesRoot = Join-Path $desktopRoot "build-resources"
$frontendSource = Join-Path $repoRoot "frontend\dist"
$backendSource = Join-Path $repoRoot "backend"
$frontendTarget = Join-Path $resourcesRoot "frontend"
$backendTarget = Join-Path $resourcesRoot "backend"

if (-not (Test-Path $frontendSource)) {
  throw "Frontend desktop build not found. Run npm --prefix frontend run build:desktop first."
}

if (Test-Path $resourcesRoot) {
  Remove-Item -LiteralPath $resourcesRoot -Recurse -Force
}
New-Item -ItemType Directory -Force $frontendTarget | Out-Null
New-Item -ItemType Directory -Force $backendTarget | Out-Null

Copy-Item -Path (Join-Path $frontendSource "*") -Destination $frontendTarget -Recurse -Force

$excludedDirectories = @(
  ".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", "htmlcov",
  ".venv", "venv", ".verify-venv", "node_modules", "dist", "build", "release", "tests", "backups"
)
$excludedFilePatterns = @("*.pyc", "*.pyo", "*.sqlite", "*.db", "*.log", ".env", ".env.*")

function Copy-CleanDirectory($Source, $Destination) {
  Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
    if ($_.PSIsContainer) {
      if ($excludedDirectories -contains $_.Name) { return }
      $nextDestination = Join-Path $Destination $_.Name
      New-Item -ItemType Directory -Force $nextDestination | Out-Null
      Copy-CleanDirectory $_.FullName $nextDestination
      return
    }

    foreach ($pattern in $excludedFilePatterns) {
      if ($_.Name -like $pattern) { return }
    }
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Destination $_.Name) -Force
  }
}

Copy-CleanDirectory $backendSource $backendTarget

Write-Host "Staged HIOP Desktop resources in $resourcesRoot"

