$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms
$serverInput = [Microsoft.VisualBasic.Interaction]::InputBox(
    'Enter the HTTPS address of your hotel HIOP server. Use the address shown on its agent download page.',
    'HIOP Agent for Windows',
    'https://'
).Trim()

if (-not $serverInput) {
    exit 0
}

try {
    $serverUri = [Uri]$serverInput
    if (-not $serverUri.IsAbsoluteUri -or
        ($serverUri.Scheme -ne 'https' -and -not ($serverUri.Scheme -eq 'http' -and $serverUri.IsLoopback)) -or
        $serverUri.UserInfo -or $serverUri.Query -or $serverUri.Fragment -or
        $serverUri.AbsolutePath -ne '/') {
        throw 'Enter a trusted HTTPS HIOP server address, such as https://hiop.example.com.'
    }

    $serverUrl = $serverUri.GetLeftPart([UriPartial]::Authority).TrimEnd('/')
    $workingRoot = Join-Path $env:TEMP ('HIOP-Agent-Install-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $workingRoot | Out-Null
    $archivePath = Join-Path $workingRoot 'agent-package.zip'
    $packageRoot = Join-Path $workingRoot 'package'

    Write-Host "Downloading the HIOP Agent package from $serverUrl ..."
    Invoke-WebRequest -Uri "$serverUrl/download/agent/package" -OutFile $archivePath -UseBasicParsing
    Expand-Archive -LiteralPath $archivePath -DestinationPath $packageRoot -Force

    $setupPath = Join-Path $packageRoot 'setup.json'
    $installScript = Join-Path $packageRoot 'install-user.ps1'
    if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $installScript -PathType Leaf)) {
        throw 'The HIOP server returned an incomplete agent package.'
    }

    $setup = Get-Content -LiteralPath $setupPath -Raw | ConvertFrom-Json
    if ($setup.backend_url.TrimEnd('/') -ne $serverUrl) {
        throw 'The downloaded agent package is configured for a different HIOP server.'
    }

    Write-Host 'Starting the HIOP Agent installation. Approve the Windows administrator prompt.'
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $installScript + '"'
    $install = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $packageRoot -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "The HIOP Agent installation failed (exit code $($install.ExitCode))."
    }

    [void][System.Windows.Forms.MessageBox]::Show(
        'HIOP Agent installed. Enter the one-time enrollment code in the HIOP Agent tray window.',
        'HIOP Agent',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    )
}
catch {
    [void][System.Windows.Forms.MessageBox]::Show(
        $_.Exception.Message,
        'HIOP Agent installation failed',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    )
    throw
}
finally {
    if ($workingRoot -and (Test-Path -LiteralPath $workingRoot)) {
        Remove-Item -LiteralPath $workingRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
