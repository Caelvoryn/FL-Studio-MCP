param(
    [ValidateRange(1024,65535)][int]$Port = 9788,
    [string]$ToPort = 'FLStudioMCP RX',
    [string]$FromPort = 'FLStudioMCP TX',
    [string]$StateDirectory = (Join-Path $env:USERPROFILE '.flstudio-mcp-system')
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create .venv and install the project first.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already occupied; existing processes will not be stopped."
}
New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
$env:FLSTUDIO_MCP_TCP_HOST = '127.0.0.1'
$env:FLSTUDIO_MCP_TCP_PORT = "$Port"
$env:FLSTUDIO_MCP_PORT_TO_FL = $ToPort
$env:FLSTUDIO_MCP_PORT_FROM_FL = $FromPort
$env:FLSTUDIO_MCP_STATE_DIR = $StateDirectory
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$launcher = Start-Process -FilePath $pythonExe -ArgumentList '-m','fl_studio_mcp.daemon' `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $StateDirectory 'daemon.stdout.log') `
    -RedirectStandardError (Join-Path $StateDirectory 'daemon.stderr.log')
$deadline = (Get-Date).AddSeconds(15)
$listener = $null
while ((Get-Date) -lt $deadline) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { break }
    Start-Sleep -Milliseconds 200
}
if (-not $listener) { throw 'Candidate did not start listening within 15 seconds. Inspect daemon.stderr.log; no existing service was changed.' }
$owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
if ($owner.ProcessId -ne $launcher.Id -and $owner.ParentProcessId -ne $launcher.Id) {
    throw 'Listener owner does not match the launched process; refusing to claim it.'
}
@{ process_id=$owner.ProcessId; creation_time=$owner.CreationDate.ToUniversalTime().ToString('o');
   port=$Port; command_line=$owner.CommandLine; project_root=$projectRoot } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StateDirectory 'owned-daemon.json') -Encoding utf8
Write-Output "Candidate bridge listening on 127.0.0.1:$Port. No client configuration was changed."
