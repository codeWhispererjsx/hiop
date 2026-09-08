$ErrorActionPreference = 'Stop'
try {
    $setup = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'setup.json') -Raw | ConvertFrom-Json
    $agentRoot = Join-Path $env:LOCALAPPDATA 'HIOP Agent'
    $agentData = Join-Path $agentRoot 'data'
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.12 from python.org/downloads/windows (include the Python launcher), then open Connect HIOP again.'
    }
    New-Item -ItemType Directory -Force -Path $agentRoot,$agentData | Out-Null
    if (Test-Path (Join-Path $agentData 'credential.dpapi')) {
        throw 'This Windows account already has a connected HIOP agent. Open Local Agents in HIOP to manage it.'
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'hiop_agent') -Destination $agentRoot -Recurse -Force
    & py -3 -m venv (Join-Path $agentRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed.' }
    $agentPython = Join-Path $agentRoot '.venv\Scripts\python.exe'
    & $agentPython -m pip install 'pywin32==311'
    if ($LASTEXITCODE -ne 0) { throw 'Agent dependency installation failed. Check your internet connection and retry.' }
    $agentConfig = Join-Path $agentData 'agent.json'
    @{backend_url=$setup.backend_url;data_dir=$agentData;heartbeat_seconds=30;poll_seconds=5} | ConvertTo-Json | Set-Content -LiteralPath $agentConfig -Encoding UTF8
    Push-Location $agentRoot
    try {
        & $agentPython -m hiop_agent.runner --config $agentConfig --enroll-prompt
        if ($LASTEXITCODE -ne 0) { throw 'Connection failed. Generate a fresh connection code in HIOP and try again.' }
    } finally { Pop-Location }
    $agentPythonw = Join-Path $agentRoot '.venv\Scripts\pythonw.exe'
    $agentArguments = '-m hiop_agent.runner --config "' + $agentConfig + '"'
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'HIOP Agent.lnk'))
    $shortcut.TargetPath = $agentPythonw
    $shortcut.Arguments = $agentArguments
    $shortcut.WorkingDirectory = $agentRoot
    $shortcut.Save()
    Start-Process -FilePath $agentPythonw -ArgumentList $agentArguments -WorkingDirectory $agentRoot -WindowStyle Hidden
    Write-Host 'Connected. Return to HIOP Local Agents and wait for Online. Keep this computer awake and signed in. HIOP will start automatically when you sign in to Windows.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
