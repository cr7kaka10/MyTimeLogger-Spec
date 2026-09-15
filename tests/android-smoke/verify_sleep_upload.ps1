param(
    [Parameter(Mandatory = $true)][string]$ServerLog,
    [string]$Serial = 'emulator-5554'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ServerLog)) { throw "Server log not found: $ServerLog" }
$adb = (Get-Command adb -ErrorAction Stop).Source
$deviceState = (& $adb -s $Serial get-state 2>&1 | Out-String).Trim()
if ($deviceState -ne 'device') { throw "Android device is not ready: $Serial" }

$logcat = & $adb -s $Serial logcat -d
if ($logcat -match '上传失败:\s*Failed to fetch|Failed to fetch') { throw 'Android logcat still contains Failed to fetch' }

$serverText = Get-Content -LiteralPath $ServerLog -Raw
$uploads = [regex]::Matches($serverText, 'Upload received:[^\r\n]*?->\s*([a-f0-9]{32})')
if ($uploads.Count -eq 0) { throw 'No Upload received request_id found in server log' }
$requestId = $uploads[$uploads.Count - 1].Groups[1].Value
$escapedId = [regex]::Escape($requestId)
if ($serverText -notmatch "(?s)(upload validation done|analysis mark done).*?request_id=$escapedId") {
    throw "No uploaded/done evidence for request_id=$requestId"
}

Write-Output "sleep upload smoke passed: request_id=$requestId status=uploaded/done serial=$Serial"
