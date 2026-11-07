$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$batch = Get-Content -Raw -LiteralPath (Join-Path $root 'start-all-pc.bat')
$wsa = Get-Content -Raw -LiteralPath (Join-Path $root 'scripts\start-wsa-dev.ps1')

foreach ($token in @(
    'scripts\bootstrap-dev.ps1',
    'scripts\start-local-process.ps1" -Name Server',
    'scripts\start-local-process.ps1" -Name Vite',
    'scripts\wait-local-readiness.ps1" -TimeoutSeconds 90',
    'scripts\start-local-process.ps1" -Name Electron',
    'scripts\start-wsa-dev.ps1',
    '[start-pc] Server: ready',
    '[start-pc] Vite: ready',
    '[start-pc] PC: ready',
    '[start-pc] Android: ready',
    'if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause'
)) {
    if (-not $batch.Contains($token)) { throw "start-all-pc contract missing: $token" }
}
if ($batch.IndexOf('Launching Electron') -ge $batch.IndexOf('Launching WSA Android')) {
    throw 'Electron must be attempted before WSA Android'
}

foreach ($token in @(
    'model:Subsystem_for_Android',
    'com.mytimelogger.app',
    'MTL_WSA_SERIAL',
    'ui\android\local.properties',
    'deploy\build-android.ps1',
    'install', '-r',
    'reverse', 'tcp:8000',
    'com.mytimelogger.app/.MainActivity',
    'wsa-*.summary.json'
)) {
    if (-not $wsa.Contains($token)) { throw "WSA startup contract missing: $token" }
}
foreach ($forbidden in @('Stop-Process', 'start-android-dev.ps1', 'emulator-5554', '-avd')) {
    if ($wsa.Contains($forbidden)) { throw "WSA startup contains forbidden operation: $forbidden" }
}

Write-Output 'start-all-pc WSA contracts passed'
