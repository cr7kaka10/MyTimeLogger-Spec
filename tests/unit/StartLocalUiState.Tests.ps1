$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$statePath = Join-Path $root 'tests\runtime\startup-logs\Vite.state.json'
$original = Get-Content -Raw -LiteralPath $statePath
$state = $original | ConvertFrom-Json
$env:MTL_STARTUP_RUN_ID = [string]$state.run_id
$ready = Join-Path $root 'scripts\wait-local-readiness.ps1'
$start = Join-Path $root 'scripts\start-local-process.ps1'

function Set-TestState($value) {
    $value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding UTF8
}
function Assert-Rejected([string]$reason) {
    $ErrorActionPreference = 'Continue'
    $null = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ready -TimeoutSeconds 1 2>&1
    if ($LASTEXITCODE -eq 0) { throw "readiness accepted $reason" }
    $electronOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $start -Name Electron 2>&1
    if ($LASTEXITCODE -eq 0) { throw "Electron accepted $reason" }
    if (($electronOutput -join ' ') -notmatch 'Vite state rejected') { throw "Electron failed for another reason: $electronOutput" }
    $ErrorActionPreference = 'Stop'
}

try {
    $state.run_id = 'stale-run-id'
    Set-TestState $state
    Assert-Rejected 'stale run id'

    $state.run_id = $env:MTL_STARTUP_RUN_ID
    $state.pid = $PID
    Set-TestState $state
    Assert-Rejected 'non-project PID'

    $state.pid = ($original | ConvertFrom-Json).pid
    $state.url = 'http://127.0.0.1:5173/'
    Set-TestState $state
    Assert-Rejected 'mismatched URL'
} finally {
    Set-Content -LiteralPath $statePath -Value $original -Encoding UTF8
}

$valid = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ready -TimeoutSeconds 10 2>&1
if ($LASTEXITCODE -ne 0) { throw "valid state failed readiness: $valid" }
Write-Output 'local UI state contracts passed'
