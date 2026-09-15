param([switch]$Force)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
function Invoke-Checked([string]$layer, [scriptblock]$command) {
    & $command
    if ($LASTEXITCODE -ne 0) { throw "$layer failed (exit $LASTEXITCODE)" }
}
 $requiredCommandShims = @{
    'core' = @('.bin\vitest.cmd', '.bin\tsc.cmd')
    'ui' = @('.bin\vite.cmd', '.bin\tsc.cmd')
    'desktop' = @('.bin\electron.cmd')
}
function Get-NpmDependencyHealth([string]$name, [string]$directory) {
    $nodeModules = Join-Path $directory 'node_modules'
    if (-not (Test-Path -LiteralPath $nodeModules)) { return [pscustomobject]@{ Ready = $false; Reason = 'missing_node_modules'; Missing = @() } }
    $nodeItem = Get-Item -LiteralPath $nodeModules -Force
    $nodePath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $nodeModules).Path)
    $workspacePath = [IO.Path]::GetFullPath($directory).TrimEnd('\') + '\'
    $target = [string]($nodeItem.Target -join ', ')
    if (($nodeItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $nodeItem.LinkType -in @('Junction', 'SymbolicLink') -or -not $nodePath.StartsWith($workspacePath, [StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Ready = $false; Reason = 'unsafe_reparse_point'; Missing = @(); Path = $nodeModules; Target = $target }
    }
    Push-Location $directory
    try {
        cmd.exe /d /c 'npm ls --depth=0 --silent >nul 2>nul'
        if ($LASTEXITCODE -ne 0) { return [pscustomobject]@{ Ready = $false; Reason = 'npm_tree_invalid'; Missing = @() } }
    } finally { Pop-Location }
    $missing = @($requiredCommandShims[$name] | Where-Object { -not (Test-Path -LiteralPath (Join-Path $nodeModules $_)) })
    if ($missing.Count) { return [pscustomobject]@{ Ready = $false; Reason = 'missing_command_shim'; Missing = $missing } }
    return [pscustomobject]@{ Ready = $true; Reason = 'ready'; Missing = @() }
}
try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python availability check failed. Install Python 3.12 or newer and ensure python is on PATH.' }
    $pythonVersion = python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]'3.12') { throw 'Python version check failed. Install Python 3.12 or newer and ensure python is on PATH.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js availability check failed. Install Node.js 20 LTS or newer and ensure node is on PATH.' }
    $nodeMajor = node -p "Number(process.versions.node.split('.')[0])"
    if ($LASTEXITCODE -ne 0 -or [int]$nodeMajor -lt 20) { throw 'Node.js version check failed. Install Node.js 20 LTS or newer and ensure node is on PATH.' }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm availability check failed. Install Node.js 20 LTS or newer and ensure npm is on PATH.' }
    cmd.exe /d /c 'python -c "import boto3,fastapi,httpx,markdown,multipart,openai,psutil,requests,uvicorn; from PIL import Image" >nul 2>nul'
    if ($Force -or $LASTEXITCODE -ne 0) {
        Write-Host '[bootstrap] Installing Python service dependencies...'
        Invoke-Checked 'Python dependencies; run python -m pip install -r requirements.txt' { python -m pip install -r (Join-Path $root 'requirements.txt') }
        Invoke-Checked 'Python import verification; run python -m pip install -r requirements.txt' { python -c "import boto3,fastapi,httpx,markdown,multipart,openai,psutil,requests,uvicorn; from PIL import Image" }
    } else { Write-Host '[bootstrap] Python dependencies already ready.' }

    foreach ($name in @('core', 'ui', 'desktop')) {
        $directory = Join-Path $root $name
        $health = Get-NpmDependencyHealth $name $directory
        if ($health.Reason -eq 'unsafe_reparse_point') { throw "$name dependency path unsafe_reparse_point: $($health.Path) -> $($health.Target)" }
        if ($Force -or -not $health.Ready) {
            Write-Host "[bootstrap] Repairing $name dependencies ($($health.Reason)) from lockfile..."
            Push-Location $directory
            try { Invoke-Checked "$name npm ci; run npm --prefix $name ci" { npm ci } } finally { Pop-Location }
            $health = Get-NpmDependencyHealth $name $directory
            if (-not $health.Ready) {
                $missing = if ($health.Missing.Count) { "; missing $($health.Missing -join ', ')" } else { '' }
                throw "$name dependency repair failed: $($health.Reason)$missing"
            }
        } else { Write-Host "[bootstrap] $name dependencies already ready." }
    }

    Push-Location (Join-Path $root 'desktop')
    try {
        cmd.exe /d /c 'npm run check:native --silent >nul 2>nul'
        if ($Force -or $LASTEXITCODE -ne 0) {
            Write-Host '[bootstrap] Rebuilding better-sqlite3 for Electron...'
            Invoke-Checked 'Electron native rebuild; run npm --prefix desktop run rebuild:native' { npm run rebuild:native }
            Invoke-Checked 'Electron ABI verification; run npm --prefix desktop run rebuild:native' { npm run check:native }
        } else { Write-Host '[bootstrap] Electron native ABI already ready.' }
    } finally { Pop-Location }
    Write-Host '[bootstrap] All required dependencies are ready.'
} catch {
    Write-Error "[bootstrap] $($_.Exception.Message)"
    exit 1
}
