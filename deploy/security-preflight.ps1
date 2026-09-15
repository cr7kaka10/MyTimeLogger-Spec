param(
    [string]$Environment = "testing",
    [string]$RepositoryRoot = ""
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = if ($RepositoryRoot) { $RepositoryRoot } else { Join-Path $PSScriptRoot ".." }

function Fail($Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

function Warn($Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

Push-Location $RepositoryRoot
try {
    $tracked = @(git -c core.quotepath=false ls-files 2>$null)
    if ($LASTEXITCODE -ne 0) { Fail "rule=git-index-unavailable path=.git" }
    foreach ($file in @(git -c core.quotepath=false ls-files -ci --exclude-standard)) {
        Fail "rule=tracked-but-ignored path=$file"
    }

    $pathRules = [ordered]@{
        "tracked-database" = '(?i)\.(?:db|sqlite|sqlite3)(?:-(?:wal|shm)|-journal)?(?:\.gz)?$'
        "tracked-backup" = '(?i)(?:\.bak(?:_|$)|\.backup$|before[-_.]|restore-candidates)'
        "personal-runtime" = '(?i)(?:^tests/runtime(?:/|$)|(^|/)(?:assets/tmp|desktop/local_data|reports|server/(?:data|log|reports|scratch))(/|$))'
    }
    $secretPattern = '(?i)^\s*(?:set\s+)?"?[A-Z0-9_-]*(?:API_KEY|ACCESS_KEY|ACCESS_TOKEN|AUTH_TOKEN|SECRET|PASSWORD|CLIENT_SECRET|WEBHOOK_URL)"?\s*(?:=|:)\s*(?<value>.*)$'
    $placeholderPattern = '(?i)^\s*(?:|<[^>]+>|(?:your|example|placeholder|changeme)[-_A-Z0-9]*|\$\{[^}]+\}|%[A-Z0-9_]+%)\s*$'
    $absolutePathPattern = '(?i)(?<![A-Z0-9])(?:[A-Z]:[\\/]|/(?:Users|home)/[^/\s]+/)'
    $personalAccountPattern = '(?i)\b[A-Z0-9._%+-]+@(?!example\.(?:com|org|net|test)\b)[A-Z0-9.-]+\.[A-Z]{2,}\b'
    $remoteAddressPattern = '(?i)https?://(?!(?:127\.0\.0\.1|localhost|\[::1\]|example\.(?:com|org|net))(?:[:/]|$))(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?'
    $textFilePattern = '(?i)(?:\.(?:ps1|bat|cmd|env|example|json|ya?ml|toml|ini|cfg|py|js|ts|tsx|md|txt|html|sh)|Dockerfile)$'
    $sourceCodePattern = '(?i)\.(?:py|js|ts|tsx|html|ps1|sh)$'
    $testSourcePattern = '(?i)(^|/)(?:tests?/|core/__tests__/|ui/src/.*(?:test|spec)\.[tj]sx?$)'
    $contentAllowlist = @("deploy/generate-private-config.ps1")
    $testFixtureAllowlist = @("tests/unit/test_security_hardening.py", "ui/src/components/Auth/LoginPage.inputContract.test.tsx")
    foreach ($file in $tracked) {
        if ($testFixtureAllowlist -contains $file -or $file -match '^(?i:(?:openspec|docs|scripts)/)' -or $file -match '(?i)\.md$') { continue }
        foreach ($rule in $pathRules.GetEnumerator()) {
            if ($file -match $rule.Value) { Fail "rule=$($rule.Key) path=$file" }
        }
        if ($contentAllowlist -contains $file -or $file -match '(^|/)package-lock\.json$' -or $file -notmatch $textFilePattern -or -not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
        if ($file -notmatch $testSourcePattern) {
            foreach ($match in @(Select-String -LiteralPath $file -Pattern $secretPattern -ErrorAction SilentlyContinue)) {
                $rawCandidate = $match.Matches[0].Groups["value"].Value.Trim().TrimEnd(',')
                if ($file -match $sourceCodePattern -and $rawCandidate -notmatch '^\s*["'']') { continue }
                $candidate = $rawCandidate.Trim('"').Trim("'")
                if ($candidate -notmatch $placeholderPattern) { Fail "rule=non-placeholder-secret path=$file" }
            }
        }
        if (Select-String -LiteralPath $file -Pattern $absolutePathPattern -Quiet -ErrorAction SilentlyContinue) {
            Fail "rule=local-absolute-path path=$file"
        }
        if (Select-String -LiteralPath $file -Pattern $personalAccountPattern -Quiet -ErrorAction SilentlyContinue) {
            Fail "rule=personal-account path=$file"
        }
        if (Select-String -LiteralPath $file -Pattern $remoteAddressPattern -Quiet -ErrorAction SilentlyContinue) {
            Fail "rule=personal-remote-address path=$file"
        }
    }
} finally {
    Pop-Location
}

$serverUrl = [Environment]::GetEnvironmentVariable("MTL_SERVER_URL", "Process")
$corsOrigins = [Environment]::GetEnvironmentVariable("MTL_CORS_ORIGINS", "Process")
$allowInsecure = [Environment]::GetEnvironmentVariable("MTL_ALLOW_INSECURE_PRODUCTION", "Process")

if ($Environment -match "^(production|prod)$") {
    if ($serverUrl -and -not $serverUrl.StartsWith("https://") -and $allowInsecure -notin @("1", "true", "yes")) {
        Fail "Production MTL_SERVER_URL must use HTTPS, or set MTL_ALLOW_INSECURE_PRODUCTION=1 explicitly."
    }
    if (-not $corsOrigins) {
        Fail "Production deployment requires MTL_CORS_ORIGINS."
    }
}

if ($Environment -match "^(testing|test)$" -and -not $corsOrigins) {
    Warn "MTL_CORS_ORIGINS is empty. Testing server will rely on backend defaults."
}

Write-Host "[OK] Security preflight passed." -ForegroundColor Green
