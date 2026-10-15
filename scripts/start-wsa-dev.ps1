param([ValidateRange(10, 300)][int]$TimeoutSeconds = 90)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$localProperties = Join-Path $root 'ui\android\local.properties'
$buildScript = Join-Path $root 'deploy\build-android.ps1'
$apkPath = Join-Path $root 'deploy\artifacts\MyTimeLogger-debug.apk'
if (-not (Test-Path -LiteralPath $localProperties -PathType Leaf)) {
    throw "WSA build preflight failed: missing $localProperties"
}
$sdkLine = Get-Content -LiteralPath $localProperties | Where-Object { $_ -match '^sdk\.dir=' } | Select-Object -First 1
if (-not $sdkLine) { throw 'WSA build preflight failed: sdk.dir is missing from local.properties.' }
$sdkRoot = ([string]$sdkLine).Substring(([string]$sdkLine).IndexOf('=') + 1).Trim().Replace('\\', '\')
if (-not (Test-Path -LiteralPath $sdkRoot -PathType Container)) {
    throw "WSA build preflight failed: SDK directory does not exist: $sdkRoot"
}
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot
$bundledJdkRoot = Join-Path $sdkRoot 'jdk'
$bundledJdk = if (Test-Path -LiteralPath $bundledJdkRoot -PathType Container) {
    Get-ChildItem -LiteralPath $bundledJdkRoot -Directory | Where-Object {
        Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') -PathType Leaf
    } | Select-Object -First 1
}
if ($bundledJdk) {
    $env:JAVA_HOME = $bundledJdk.FullName
    $env:PATH = "$(Join-Path $bundledJdk.FullName 'bin');$env:PATH"
}
$appId = 'com.mytimelogger.app'
$defaultSerial = '127.0.0.1:58526'
$adbCandidates = @((Join-Path $sdkRoot 'platform-tools\adb.exe'), 'C:\adb\adb.exe')
if ($env:ANDROID_SDK_ROOT) { $adbCandidates += Join-Path $env:ANDROID_SDK_ROOT 'platform-tools\adb.exe' }
if ($env:ANDROID_HOME) { $adbCandidates += Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe' }
$adb = $adbCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $adb) { throw 'WSA preflight failed: adb.exe was not found.' }

function Get-OnlineWsaSerials {
    $lines = & $adb devices -l
    if ($LASTEXITCODE -ne 0) { throw 'WSA preflight failed: adb devices failed.' }
    return @($lines | Where-Object { $_ -match '^\S+\s+device\b.*model:Subsystem_for_Android' } |
        ForEach-Object { ([regex]::Match($_, '^\S+')).Value })
}

function Get-TargetWsaSerial {
    $requested = if ($env:MTL_WSA_SERIAL) { $env:MTL_WSA_SERIAL } else { '' }
    if ($requested) { & $adb connect $requested | Out-Host }
    $online = @(Get-OnlineWsaSerials)
    if ($requested -and $requested -in $online) { return $requested }
    if ($requested) { throw "WSA identity check failed for MTL_WSA_SERIAL=$requested." }
    if ($online.Count -eq 1) { return $online[0] }
    if ($online.Count -gt 1) { throw 'Multiple WSA devices found; set MTL_WSA_SERIAL explicitly.' }

    $registered = Get-StartApps | Where-Object { $_.AppID -eq $appId } | Select-Object -First 1
    if (-not $registered) { throw "WSA app is not registered in Windows: $appId" }
    Start-Process -FilePath 'explorer.exe' -ArgumentList "shell:AppsFolder\$appId"
    & $adb connect $defaultSerial | Out-Host
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $online = @(Get-OnlineWsaSerials)
        if ($online.Count -eq 1) { return $online[0] }
        if ($online.Count -gt 1) { throw 'Multiple WSA devices found after launch; set MTL_WSA_SERIAL explicitly.' }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "WSA transport did not become ready at $defaultSerial within $TimeoutSeconds seconds."
}

$serial = Get-TargetWsaSerial
Write-Host "[wsa] Target ready: $serial (model:Subsystem_for_Android)."
Write-Host "[wsa] Building current Android workspace with SDK $sdkRoot."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildScript
if ($LASTEXITCODE -ne 0) { throw "WSA build stage failed (exit $LASTEXITCODE)." }
if (-not (Test-Path -LiteralPath $apkPath -PathType Leaf)) {
    throw "WSA build stage did not produce APK: $apkPath"
}
Write-Host "[wsa] APK ready: $apkPath"
