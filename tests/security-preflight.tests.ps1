$ErrorActionPreference = "Stop"
$preflight = (Resolve-Path (Join-Path $PSScriptRoot "..\deploy\security-preflight.ps1")).Path
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$powershellExecutable = (Get-Command powershell.exe -CommandType Application | Select-Object -First 1 -ExpandProperty Source)
$roots = [System.Collections.Generic.List[string]]::new()

function Assert-True($Condition, $Message) {
    if (-not $Condition) { throw $Message }
}

function New-FixtureRepo([hashtable]$Files, [string[]]$ForceAdd = @()) {
    $root = Join-Path ([IO.Path]::GetTempPath()) ("mtl-preflight-" + [guid]::NewGuid().ToString("N"))
    $roots.Add($root)
    New-Item -ItemType Directory -Path $root | Out-Null
    git -C $root init --quiet
    foreach ($entry in $Files.GetEnumerator()) {
        $target = Join-Path $root $entry.Key
        New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
        Set-Content -LiteralPath $target -Value $entry.Value -Encoding UTF8
    }
    git -C $root add --all 2>$null
    foreach ($path in $ForceAdd) { git -C $root add -f -- $path }
    return $root
}

function Invoke-Preflight($Root) {
    $output = & $powershellExecutable -NoProfile -ExecutionPolicy Bypass -File $preflight -Environment development -RepositoryRoot $Root 2>&1 | Out-String
    return [pscustomobject]@{ Code = $LASTEXITCODE; Output = $output }
}

try {
    $safe = Invoke-Preflight (New-FixtureRepo @{ "safe.env" = "API_KEY=<your-api-key>" })
    Assert-True ($safe.Code -eq 0) "placeholder fixture should pass"

    $secretValue = "fixture" + "-credential-material"
    $secret = Invoke-Preflight (New-FixtureRepo @{ "unsafe.env" = "API_KEY=$secretValue" })
    Assert-True ($secret.Code -ne 0 -and $secret.Output -match 'rule=non-placeholder-secret path=unsafe.env') "secret fixture should fail redacted"
    Assert-True ($secret.Output -notmatch [regex]::Escape($secretValue)) "secret fixture leaked"

    $absoluteValue = "C" + ":\private\reports"
    $absolute = Invoke-Preflight (New-FixtureRepo @{ "settings.txt" = "REPORTS_DIR=$absoluteValue" })
    Assert-True ($absolute.Code -ne 0 -and $absolute.Output -match 'rule=local-absolute-path path=settings.txt') "absolute path fixture should fail"
    Assert-True ($absolute.Output -notmatch [regex]::Escape($absoluteValue)) "absolute path fixture leaked"

    $database = Invoke-Preflight (New-FixtureRepo @{ "sample.db" = "fixture" })
    Assert-True ($database.Code -ne 0 -and $database.Output -match 'rule=tracked-database path=sample.db') "tracked database fixture should fail"
    $ignored = Invoke-Preflight (New-FixtureRepo @{ ".gitignore" = "private.env"; "private.env" = "fixture" } @("private.env"))
    Assert-True ($ignored.Code -ne 0 -and $ignored.Output -match 'rule=tracked-but-ignored path=private.env') "forced ignored fixture should fail"

    $trackedIgnored = @(git -C $repositoryRoot -c core.quotepath=false ls-files -ci --exclude-standard)
    Assert-True ($trackedIgnored.Count -eq 0) "tracked source, tests, and OpenSpec documents must not be ignored"
    foreach ($path in @("core/__tests__/AccountIdentity.test.ts", "openspec/changes/archive/2026-06-18-chg-20260612-003-timer-fix-and-refactor/proposal.md")) {
        git -C $repositoryRoot check-ignore -q --no-index -- $path
        Assert-True ($LASTEXITCODE -ne 0) "tracked engineering asset must not be ignored: $path"
    }

    Write-Host "[PASS] security preflight fixtures and repository tracking boundary"
} finally {
    foreach ($root in $roots) { if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force } }
}
