param([string]$ActivationUrl = "", [string]$OrganizationCode = "", [string]$LicenseKey = "")
$ErrorActionPreference = "Stop"
$desktopData = Join-Path $env:LOCALAPPDATA "HIOP Desktop"
New-Item -ItemType Directory -Force $desktopData | Out-Null
$config = [ordered]@{
  activation_url = $ActivationUrl
  organization_code = $OrganizationCode
  license_key = $LicenseKey
  configured_at = (Get-Date).ToString("o")
  status = if ($ActivationUrl -and $LicenseKey) { "configured" } else { "local_only" }
}
$config | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $desktopData "activation.json")
Write-Host "Activation settings saved."
