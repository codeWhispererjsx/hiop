param(
    [string]$DotnetPath = (Join-Path $env:ProgramFiles 'dotnet\dotnet.exe')
)

$ErrorActionPreference = 'Stop'
$agentRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $agentRoot
$serviceProject = Join-Path $agentRoot 'Hiop.Agent.Service\Hiop.Agent.Service.csproj'
$trayProject = Join-Path $agentRoot 'Hiop.Agent.Tray\Hiop.Agent.Tray.csproj'
$distribution = Join-Path $repoRoot 'backend\app\distributions'
$bundle = Join-Path $distribution 'hiop-agent-windows.zip'
$staging = Join-Path $env:TEMP ('hiop-agent-package-' + [Guid]::NewGuid().ToString('N'))

if (-not (Test-Path -LiteralPath $DotnetPath)) {
    $command = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if (-not $command) {
        throw 'The .NET 10 SDK is required to build the HIOP Windows agent.'
    }
    $DotnetPath = $command.Source
}

New-Item -ItemType Directory -Force -Path $staging,(Join-Path $staging 'service'),(Join-Path $staging 'tray') | Out-Null
try {
    & $DotnetPath publish $serviceProject --configuration Release --runtime win-x64 --self-contained true `
        -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:EnableCompressionInSingleFile=true --output (Join-Path $staging 'service')
    if ($LASTEXITCODE -ne 0) {
        throw 'The HIOP Windows service publish failed.'
    }

    & $DotnetPath publish $trayProject --configuration Release --runtime win-x64 --self-contained true `
        -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:EnableCompressionInSingleFile=true --output (Join-Path $staging 'tray')
    if ($LASTEXITCODE -ne 0) {
        throw 'The HIOP Windows tray app publish failed.'
    }

    foreach ($outputDirectory in @((Join-Path $staging 'service'),(Join-Path $staging 'tray'))) {
        Get-ChildItem -LiteralPath $outputDirectory -File |
            Where-Object { $_.Extension -eq '.pdb' -or $_.Name -like 'appsettings*.json' } |
            Remove-Item -Force
    }

    foreach ($executable in @(
        (Join-Path $staging 'service\Hiop.Agent.Service.exe'),
        (Join-Path $staging 'tray\Hiop.Agent.Tray.exe')
    )) {
        if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
            throw "The native agent publish did not produce $executable."
        }
    }

    Copy-Item -LiteralPath (Join-Path $distribution 'install-user.ps1') -Destination $staging
    Copy-Item -LiteralPath (Join-Path $distribution 'uninstall-user.ps1') -Destination $staging
    Copy-Item -LiteralPath (Join-Path $distribution 'Install HIOP Agent.cmd') -Destination $staging
    Copy-Item -LiteralPath (Join-Path $distribution 'Remove HIOP Agent.cmd') -Destination $staging

    if (Test-Path -LiteralPath $bundle) {
        Remove-Item -LiteralPath $bundle -Force
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $staging,
        $bundle,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
    Write-Host "Created native Windows agent package: $bundle"
} finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
