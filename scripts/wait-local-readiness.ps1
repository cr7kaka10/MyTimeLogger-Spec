param(
    [string]$ServerUrl = 'http://127.0.0.1:8000/ping',
    [string]$UiUrl = 'http://127.0.0.1:5173/',
    [ValidateRange(1, 600)][int]$TimeoutSeconds = 90,
    [switch]$RequirePortsFree
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDirectory = Join-Path $root 'tests\runtime\startup-logs'
$expectedBuild = ''
try { $expectedBuild = (& git -C $root rev-parse --short=12 HEAD 2>$null).Trim() } catch {}
$finalBackupVersion = 2
$allowedHosts = @('localhost', '127.0.0.1', '::1', '[::1]')
foreach ($candidate in @($ServerUrl, $UiUrl)) {
    try { $uri = [Uri]$candidate } catch { Write-Error '[readiness] Invalid URL' -ErrorAction Continue; exit 2 }
    if ($uri.Scheme -notin @('http', 'https') -or $uri.Host -notin $allowedHosts) {
        Write-Error '[readiness] Only loopback HTTP(S) URLs are allowed' -ErrorAction Continue
        exit 2
    }
}

if ($RequirePortsFree) {
    foreach ($port in @(([Uri]$ServerUrl).Port, ([Uri]$UiUrl).Port)) {
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
            Write-Error "[readiness] Required localhost port $port is already in use" -ErrorAction Continue
            exit 3
        }
    }
    Write-Host '[readiness] Required localhost ports are free.'
    exit 0
}

function Test-Endpoint([string]$url, [switch]$RequireOkStatus) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) { return $false }
        if (-not $RequireOkStatus) { return $true }
        $readiness = $response.Content | ConvertFrom-Json
        return (
            ($readiness.status -eq 'ok') -and
            ([int]$readiness.capabilities.atimelogger_final_backup.version -eq $finalBackupVersion) -and
            ((-not $expectedBuild) -or ($readiness.build_revision -eq $expectedBuild))
        )
    } catch { return $false }
}

function Get-TrackedProjectProcess([string]$name) {
    $statePath = Join-Path $logDirectory "$name.state.json"
    if (-not (Test-Path -LiteralPath $statePath)) { return [pscustomobject]@{ Valid = $false; Reason = 'missing_state'; StatePath = $statePath } }
    try { $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json } catch { return [pscustomobject]@{ Valid = $false; Reason = 'invalid_state'; StatePath = $statePath } }
    if ($state.endpoint -ne $name -or -not $state.pid -or ($env:MTL_STARTUP_RUN_ID -and $state.run_id -ne $env:MTL_STARTUP_RUN_ID)) { return [pscustomobject]@{ Valid = $false; Reason = 'stale_state'; State = $state; StatePath = $statePath } }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.pid)" -ErrorAction SilentlyContinue
    if (-not $processInfo) { return [pscustomobject]@{ Valid = $false; Reason = 'process_exited'; State = $state; StatePath = $statePath } }
    $commandLine = [string]$processInfo.CommandLine
    $belongs = if ($name -eq 'Server') { $commandLine -match 'uvicorn\s+server\.server:app' } else {
        ($commandLine -like "*$root*" -and $commandLine -match 'vite') -or $commandLine -match 'cmd\.exe"?\s+/d\s+/c\s+npm\s+run\s+dev'
    }
    if (-not $belongs) { return [pscustomobject]@{ Valid = $false; Reason = 'process_not_project_owned'; State = $state; StatePath = $statePath } }
    return [pscustomobject]@{ Valid = $true; State = $state; StatePath = $statePath }
}

function Format-StartupLogTail($path) {
    if (-not $path -or -not (Test-Path -LiteralPath $path)) { return '(log unavailable)' }
    return ((Get-Content -LiteralPath $path -Tail 10 | ForEach-Object { $_.Substring(0, [Math]::Min($_.Length, 300)) }) -join ' | ')
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    $serverProcess = Get-TrackedProjectProcess 'Server'
    $viteProcess = Get-TrackedProjectProcess 'Vite'
    if (-not $serverProcess.Valid -or -not $viteProcess.Valid) {
        $failed = if (-not $serverProcess.Valid) { $serverProcess } else { $viteProcess }
        $endpoint = if ($failed -eq $serverProcess) { 'Server' } else { 'Vite' }
        $stderrPath = $failed.State.stderr_path
        Write-Error "[readiness] process_exited_before_ready endpoint=$endpoint reason=$($failed.Reason) logs=$stderrPath tail=$(Format-StartupLogTail $stderrPath)" -ErrorAction Continue
        exit 4
    }
    $serverReady = Test-Endpoint $ServerUrl -RequireOkStatus
    $uiReady = Test-Endpoint $UiUrl
    if ($serverReady -and $uiReady) {
        Write-Host '[readiness] FastAPI /ping and Vite are ready.'
        exit 0
    }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)

Write-Error "[readiness] Timed out after $TimeoutSeconds seconds (server=$serverReady, ui=$uiReady)" -ErrorAction Continue
exit 1
