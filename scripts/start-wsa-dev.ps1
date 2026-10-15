param([ValidateRange(10, 300)][int]$TimeoutSeconds = 90)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appId = 'com.mytimelogger.app'
$defaultSerial = '127.0.0.1:58526'
$adbCandidates = @('C:\adb\adb.exe')
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
