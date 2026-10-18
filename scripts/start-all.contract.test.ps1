$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script = Get-Content -Raw -LiteralPath (Join-Path $root 'start-all.bat')
$androidScript = Get-Content -Raw -LiteralPath (Join-Path $root 'scripts\start-android-dev.ps1')

foreach ($token in @(
    '[start] Android ready: device={0}; log={1}; summary={2}',
    '[start] Android failure: stage={0} category={1} reason={2}',
    '[start] Local startup summary:',
    '[start] PC: ready',
    '[start] PC: failed',
    'if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause',
    'exit /b %START_EXIT%'
)) {
    if (-not $script.Contains($token)) { throw "start-all contract missing: $token" }
}

if ($script.IndexOf('[start] Launching Electron...') -ge $script.IndexOf('[start] Launching Android development client...')) {
    throw 'start-all must attempt Electron before Android so Android cannot block PC'
}

foreach ($token in @(
    "activity_not_foreground",
    "activity_window_not_visible",
    "system_window_unstable",
    "init.svc.bootanim",
    'systemStableSamples -ge 2',
    "shell am start -W -n 'com.mytimelogger.app/.MainActivity'",
    'shell dumpsys activity activities',
    'topResumedActivity|mResumedActivity',
    'shell dumpsys window windows',
    'Surface:\s+shown=true',
    'Wait-AndroidAppReady',
    'appRecoveryCount -lt 1'
)) {
    if (-not $androidScript.Contains($token)) { throw "android startup contract missing: $token" }
}

foreach ($scenario in @('transport_reconnected','transport_cold_recovered','transport_identity_unknown')) {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\start-android-dev.ps1') -DryRun -TestScenario $scenario 2>&1
    if ($scenario -ne 'transport_identity_unknown' -and $LASTEXITCODE -ne 0) { throw "$scenario dry-run failed: $output" }
    if ($scenario -eq 'transport_identity_unknown' -and $LASTEXITCODE -eq 0) { throw 'unknown target identity must fail without stopping a process' }
}
foreach ($token in @('Stop-Process -Id $confirmedPid','transportRecoveryCount -ge 1','target_avd_identity_unconfirmed')) {
    if (-not $androidScript.Contains($token)) { throw "target transport recovery contract missing: $token" }
}

Write-Output 'start-all contracts passed'
