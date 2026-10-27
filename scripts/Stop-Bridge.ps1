param([string]$StateDirectory = (Join-Path $env:USERPROFILE '.flstudio-mcp-system'))
$ErrorActionPreference = 'Stop'
$metadataPath = Join-Path $StateDirectory 'owned-daemon.json'
if (-not (Test-Path -LiteralPath $metadataPath)) { throw 'No owned daemon metadata; refusing to stop any process.' }
$owned = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$running = Get-CimInstance Win32_Process -Filter "ProcessId=$($owned.process_id)"
if (-not $running) { Write-Output 'Owned process is already stopped.'; exit 0 }
if ($running.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$owned.creation_time).ToUniversalTime().Ticks -or
    $running.CommandLine -ne $owned.command_line -or
    $running.CommandLine -notmatch 'fl_studio_mcp\.daemon') {
    throw 'Process identity differs from launch record; refusing to stop it.'
}
Stop-Process -Id $running.ProcessId
Write-Output 'Stopped the recorded candidate daemon only.'
