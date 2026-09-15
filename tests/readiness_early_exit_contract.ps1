$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logs = Join-Path $root 'tests\runtime\startup-logs'
$serverStatePath = Join-Path $logs 'Server.state.json'
$viteStatePath = Join-Path $logs 'Vite.state.json'
$originalViteState = Get-Content -Raw -LiteralPath $viteStatePath
try {
    $serverState = Get-Content -Raw -LiteralPath $serverStatePath | ConvertFrom-Json
    [pscustomobject]@{
        run_id = $serverState.run_id; pid = 999999; endpoint = 'Vite'
        started_at_beijing = '2026-09-10T00:00:00+08:00'
        stdout_path = (Join-Path $logs 'Vite.out.log'); stderr_path = (Join-Path $logs 'Vite.err.log')
    } | ConvertTo-Json | Set-Content -LiteralPath $viteStatePath -Encoding utf8
    $env:MTL_STARTUP_RUN_ID = $serverState.run_id
    $before = [Diagnostics.Stopwatch]::StartNew()
    $previousPreference = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\wait-local-readiness.ps1') -TimeoutSeconds 90 2>&1
    $exitCode = $LASTEXITCODE; $ErrorActionPreference = $previousPreference
    $before.Stop(); $text = $output -join [Environment]::NewLine
    if ($exitCode -eq 0 -or $before.Elapsed.TotalSeconds -ge 5) { throw "early exit was not fast: exit=$exitCode elapsed=$($before.Elapsed.TotalSeconds)" }
    if ($text -notmatch 'process_exited_before_ready.*Vite' -or $text -notmatch 'Vite.err.log') { throw "missing early-exit evidence: $text" }
    Write-Output 'readiness early-exit contract passed'
} finally { Set-Content -LiteralPath $viteStatePath -Value $originalViteState -Encoding utf8 }
