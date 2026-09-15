$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$loader = Join-Path $root "deploy\load-private-env.ps1"
$temp = Join-Path ([IO.Path]::GetTempPath()) ("mtl-deploy-config-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temp | Out-Null

function Assert-True([bool]$condition, [string]$message) {
    if (-not $condition) { throw $message }
}

try {
    $canonical = Join-Path $temp "config.local.env"
    @(
        "MTL_SERVER_HOST=example.com",
        "MTL_SERVER_USER=deploy-user",
        "MTL_REMOTE_DIR=/opt/mytimelogger",
        "MTL_APP_PORT=8000",
        "MTL_USERNAME=must-not-load",
        "MTL_SERVER_URL=https://must-not-load.example"
    ) | Set-Content -LiteralPath $canonical -Encoding UTF8
    $output = & $loader -Environment testing -ConfigRoot $temp -RequireComplete -Quiet -EmitCmd
    Assert-True (($output -join "`n") -match 'MTL_CONFIG_LOAD_OK=1') "canonical config did not load"
    Assert-True (($output -join "`n") -notmatch 'MTL_USERNAME|MTL_SERVER_URL') "client defaults leaked"
    Assert-True (($output -join "`n") -match 'MYTIMELOGGER_ENVIRONMENT=testing') "canonical environment missing"

    $legacy = Join-Path $temp "config.testing.local.env"
    Set-Content -LiteralPath $legacy -Value "MTL_SERVER_HOST=ignored.example" -Encoding UTF8
    $preferred = & $loader -Environment testing -ConfigRoot $temp -RequireComplete -Quiet -EmitCmd
    Assert-True (($preferred -join "`n") -match 'MTL_CONFIG_LOAD_OK=1') "canonical did not beat legacy"
    $explicit = Join-Path $temp "explicit.env"
    (Get-Content -LiteralPath $canonical) -replace 'example.com', 'explicit.example' | Set-Content -LiteralPath $explicit -Encoding UTF8
    $explicitOutput = & $loader -Environment testing -ConfigRoot $temp -ConfigPath $explicit -RequireComplete -Quiet -EmitCmd
    Assert-True (($explicitOutput -join "`n") -match 'MTL_SERVER_HOST=explicit.example') "explicit config did not win"
    Remove-Item -LiteralPath $explicit, $legacy
    Move-Item -LiteralPath $canonical -Destination $legacy
    $warnings = & $loader -Environment testing -ConfigRoot $temp -RequireComplete 3>&1
    Assert-True (($warnings -join "`n") -match 'Deprecated') "legacy warning missing"

    Remove-Item -LiteralPath $legacy
    try { & $loader -Environment testing -ConfigRoot $temp -RequireComplete -Quiet; throw "missing config accepted" }
    catch { Assert-True ($_.Exception.Message -match 'not found') "unexpected missing-config error" }

    $batch = Get-Content -Raw -LiteralPath (Join-Path $root "deploy\deploy-test.bat")
    Assert-True ($batch -match '-EmitCmd') "batch does not use the shared loader"
    Assert-True ($batch -notmatch 'config\.testing\.local\.env|VITE_MTL_TESTING_(SERVER_URL|USERNAME)') "legacy client defaults remain"
    Assert-True ($batch -match 'ENVIRONMENT=testing') "remote environment is not propagated"
    Write-Output "deploy-config-smoke: PASS"
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
