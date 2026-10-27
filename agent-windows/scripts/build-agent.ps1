param(
    [string]$DotnetPath = (Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'),
    [string]$NsisPath = ''
)

$ErrorActionPreference = 'Stop'
$agentRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $agentRoot
$serviceProject = Join-Path $agentRoot 'Hiop.Agent.Service\Hiop.Agent.Service.csproj'
$trayProject = Join-Path $agentRoot 'Hiop.Agent.Tray\Hiop.Agent.Tray.csproj'
$configurationFile = Join-Path $agentRoot 'Hiop.Agent.Core\AgentConfiguration.cs'
$installerScript = Join-Path $PSScriptRoot 'install-agent.ps1'
$installerDefinition = Join-Path $PSScriptRoot 'agent-installer.nsi'
$distribution = Join-Path $repoRoot 'backend\app\distributions'
$bundle = Join-Path $distribution 'hiop-agent-windows.zip'
$installer = Join-Path $distribution 'HIOP-Agent-Windows.exe'
$staging = Join-Path $env:TEMP ('hiop-agent-package-' + [Guid]::NewGuid().ToString('N'))

if (-not (Test-Path -LiteralPath $DotnetPath)) {
    $command = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if (-not $command) {
        throw 'The .NET 10 SDK is required to build the HIOP Windows agent.'
    }
    $DotnetPath = $command.Source
}

if (-not $NsisPath) {
    $nsisCommand = Get-Command makensis.exe -ErrorAction SilentlyContinue
    if ($nsisCommand) {
        $NsisPath = $nsisCommand.Source
    } else {
        $cachedNsis = Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'electron-builder\Cache') `
            -Directory -Filter 'nsis-*' -ErrorAction SilentlyContinue |
            ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter 'makensis.exe' -File -Recurse -ErrorAction SilentlyContinue } |
            Select-Object -First 1
        if ($cachedNsis) {
            $NsisPath = $cachedNsis.FullName
        }
    }
}
if (-not $NsisPath -or -not (Test-Path -LiteralPath $NsisPath -PathType Leaf)) {
    throw 'NSIS makensis.exe is required to build the single-file agent installer. Install NSIS or provide -NsisPath.'
}

$configurationSource = Get-Content -LiteralPath $configurationFile -Raw
if ($configurationSource -notmatch 'public const string Version = "(\d+\.\d+\.\d+)";') {
    throw "Could not read the HIOP Agent version from $configurationFile."
}
$agentVersion = $Matches[1]

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
    Add-Type -AssemblyName System.IO.Compression
    $archiveStream = [System.IO.File]::Open($bundle, [System.IO.FileMode]::CreateNew)
    $archive = [System.IO.Compression.ZipArchive]::new(
        $archiveStream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $true
    )
    try {
        foreach ($file in Get-ChildItem -LiteralPath $staging -File -Recurse) {
            $entryName = $file.FullName.Substring($staging.Length).TrimStart('\').Replace('\', '/')
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $sourceStream = [System.IO.File]::OpenRead($file.FullName)
            $entryStream = $entry.Open()
            try {
                $sourceStream.CopyTo($entryStream)
            } finally {
                $entryStream.Dispose()
                $sourceStream.Dispose()
            }
        }
    } finally {
        $archive.Dispose()
        $archiveStream.Dispose()
    }
    Write-Host "Created native Windows agent package: $bundle"

    if (-not (Test-Path -LiteralPath $installerScript -PathType Leaf)) {
        throw "The HIOP Agent installer bootstrap script is missing: $installerScript"
    }
    if (-not (Test-Path -LiteralPath $installerDefinition -PathType Leaf)) {
        throw "The HIOP Agent installer definition is missing: $installerDefinition"
    }
    if (Test-Path -LiteralPath $installer) {
        Remove-Item -LiteralPath $installer -Force
    }
    & $NsisPath "/DOUTPUT_FILE=$installer" "/DBOOTSTRAP_SCRIPT=$installerScript" `
        "/DPRODUCT_VERSION=$agentVersion" $installerDefinition
    if ($LASTEXITCODE -ne 0) {
        throw 'NSIS failed to create the HIOP Windows agent installer.'
    }

    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw "The native agent installer was not created at $installer."
    }
    Write-Host "Created single-file Windows agent installer: $installer"
} finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
