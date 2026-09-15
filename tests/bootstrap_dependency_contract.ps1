$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$fixture = Join-Path ([System.IO.Path]::GetTempPath()) "mtl-bootstrap-contract-$PID"
$originalPath = $env:Path
$originalLog = $env:MTL_NPM_LOG
$originalFixture = $env:MTL_FIXTURE
$bootstrapSource = Get-Content -Raw -LiteralPath (Join-Path $root 'scripts\bootstrap-dev.ps1')
$protectedFiles = @('core\node_modules\.bin\vitest.cmd', 'ui\node_modules\.bin\vite.cmd', 'desktop\node_modules\.bin\electron.cmd')
$protectedHashes = @{}
foreach ($path in $protectedFiles) { $protectedHashes[$path] = (Get-FileHash -LiteralPath (Join-Path $root $path)).Hash }
foreach ($entry in @('ui.*vite\.cmd', 'ui.*tsc\.cmd', 'core.*vitest\.cmd', 'core.*tsc\.cmd', 'desktop.*electron\.cmd')) {
    if ($bootstrapSource -notmatch $entry) { throw "required command mapping missing: $entry" }
}
try {
    foreach ($path in @('scripts', 'core\node_modules\.bin', 'ui\node_modules\vite', 'ui\node_modules\.bin', 'desktop\node_modules\.bin', 'fake-bin')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $fixture $path) | Out-Null
    }
    Copy-Item (Join-Path $root 'scripts\bootstrap-dev.ps1') (Join-Path $fixture 'scripts\bootstrap-dev.ps1')
    Set-Content -LiteralPath (Join-Path $fixture 'ui\node_modules\vite\package.json') -Value '{}'
    $npmLog = Join-Path $fixture 'npm.log'
    Set-Content -LiteralPath (Join-Path $fixture 'core\node_modules\.bin\vitest.cmd') -Value ''
    Set-Content -LiteralPath (Join-Path $fixture 'core\node_modules\.bin\tsc.cmd') -Value ''
    Set-Content -LiteralPath (Join-Path $fixture 'ui\node_modules\.bin\tsc.cmd') -Value ''
    Set-Content -LiteralPath (Join-Path $fixture 'desktop\node_modules\.bin\electron.cmd') -Value ''
    $npmStub = @'
@echo off
echo %*>> "%MTL_NPM_LOG%"
if /I "%1"=="ci" (
  > "%MTL_FIXTURE%\ui\node_modules\.bin\vite.cmd" echo @echo off
  >> "%MTL_FIXTURE%\ui\node_modules\.bin\vite.cmd" echo echo vite 5.4.0
)
exit /b 0
'@
    Set-Content -LiteralPath (Join-Path $fixture 'fake-bin\npm.cmd') -Value $npmStub
    $env:MTL_NPM_LOG = $npmLog
    $env:MTL_FIXTURE = $fixture
    $env:Path = "$(Join-Path $fixture 'fake-bin');$originalPath"
    if ((Get-Item -LiteralPath (Join-Path $fixture 'ui\node_modules')).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'fixture node_modules must be a normal directory' }
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'scripts\bootstrap-dev.ps1') 2>&1
    $outputText = $output -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0) { throw "fixture bootstrap unexpectedly failed: $output" }
    if ($outputText -notmatch '\[bootstrap\] Repairing ui dependencies \(missing_command_shim\) from lockfile\.') { throw "missing vite.cmd did not enter repair: $outputText" }
    if ((Get-Content -Raw -LiteralPath $npmLog) -notmatch 'ci') { throw 'missing vite.cmd did not run npm ci' }
    if (-not (Test-Path -LiteralPath (Join-Path $fixture 'ui\node_modules\.bin\vite.cmd'))) { throw 'npm ci did not restore vite.cmd' }
    $viteVersion = & (Join-Path $fixture 'ui\node_modules\.bin\vite.cmd') --version
    if ($LASTEXITCODE -ne 0 -or $viteVersion -notmatch 'vite') { throw "restored vite command did not run: $viteVersion" }
    if ($outputText -match 'Vite started') { throw 'dependency precheck must not start Vite' }
    foreach ($path in $protectedFiles) {
        if ((Get-FileHash -LiteralPath (Join-Path $root $path)).Hash -ne $protectedHashes[$path]) { throw "real dependency sentinel changed: $path" }
    }
    Clear-Content -LiteralPath $npmLog
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'scripts\bootstrap-dev.ps1') 2>&1
    if ($LASTEXITCODE -ne 0) { throw "complete fixture bootstrap unexpectedly failed: $output" }
    $npmCalls = Get-Content -Raw -LiteralPath $npmLog
    if ($npmCalls -match 'ci') { throw 'complete dependency fast path unexpectedly ran npm ci' }
    if ($npmCalls -notmatch 'run check:native') { throw 'desktop native ABI gate was not run' }
    $unsafeTarget = Join-Path $fixture 'outside-dependency-target'
    $unsafeSentinel = Join-Path $unsafeTarget 'sentinel.txt'
    New-Item -ItemType Directory -Force -Path $unsafeTarget | Out-Null
    Set-Content -LiteralPath $unsafeSentinel -Value 'must-not-change'
    $sentinelHash = (Get-FileHash -LiteralPath $unsafeSentinel).Hash
    Remove-Item -LiteralPath (Join-Path $fixture 'ui\node_modules') -Recurse -Force
    New-Item -ItemType Junction -Path (Join-Path $fixture 'ui\node_modules') -Target $unsafeTarget | Out-Null
    Clear-Content -LiteralPath $npmLog
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'scripts\bootstrap-dev.ps1') 2>&1
    $bootstrapExit = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    $outputText = $output -join [Environment]::NewLine
    if ($bootstrapExit -eq 0 -or $outputText -notmatch 'unsafe_reparse_point') { throw "junction was not rejected: $outputText" }
    if ((Get-Content -Raw -LiteralPath $npmLog) -match 'ci') { throw 'junction path attempted npm ci' }
    if ((Get-FileHash -LiteralPath $unsafeSentinel).Hash -ne $sentinelHash) { throw 'junction target sentinel changed' }
    Write-Output 'isolated missing-vite-shim recovery contract passed'
} finally {
    $env:Path = $originalPath
    $env:MTL_NPM_LOG = $originalLog
    $env:MTL_FIXTURE = $originalFixture
    $fixtureNodeModules = Join-Path $fixture 'ui\node_modules'
    if ((Test-Path -LiteralPath $fixtureNodeModules) -and ((Get-Item -LiteralPath $fixtureNodeModules -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { [IO.Directory]::Delete($fixtureNodeModules) }
    if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
