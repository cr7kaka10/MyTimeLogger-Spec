$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$picker = Join-Path $root 'scripts\select-local-ui-port.ps1'
$loopback = [Net.IPAddress]::Parse('127.0.0.1')

function Get-FreePort {
    $probe = [Net.Sockets.TcpListener]::new($loopback, 0)
    try { $probe.Start(); return ([Net.IPEndPoint]$probe.LocalEndpoint).Port }
    finally { $probe.Stop() }
}

$first = Get-FreePort
do { $second = Get-FreePort } while ($second -eq $first)
$selected = & $picker -Candidates @($first, $second)
if ($LASTEXITCODE -ne 0 -or [int]$selected -ne $first) { throw 'available preferred port was not selected' }

$blocker = [Net.Sockets.TcpListener]::new($loopback, $first)
try {
    $blocker.Start()
    $fallback = & $picker -Candidates @($first, $second)
    if ($LASTEXITCODE -ne 0 -or [int]$fallback -ne $second) { throw 'occupied preferred port did not fall back' }
    $null = & $picker -Candidates @($first) 2>$null
    if ($LASTEXITCODE -ne 2) { throw 'exhausted candidates did not fail immediately' }
    if (-not $blocker.Server.IsBound) { throw 'unknown listener was changed' }
} finally { $blocker.Stop() }

Write-Output 'local UI port selection contracts passed'
