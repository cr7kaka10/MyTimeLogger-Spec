param(
  [string]$Root = (Split-Path -Parent $PSScriptRoot),
  [string]$OutputDir = "",
  [switch]$NoPause
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
$RunId = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $OutputDir) {
  $OutputDir = Join-Path $Root "tests\runtime\sync-regression\$RunId"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$LogFile = Join-Path $OutputDir 'sync-regression-console.log'

function Write-Log {
  param([string]$Message)
  $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
  Write-Host $line
  Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

try {
  Write-Host '============================================================'
  Write-Host 'MyTimeLogger 同步回归测试套件（离线 Fake TickTick，不改真实数据）'
  Write-Host "Root: $Root"
  Write-Host "Output: $OutputDir"
  Write-Host '============================================================'

  Write-Log '开始运行同步回归测试'
  $script = Join-Path $Root 'scripts\sync-regression-suite.py'
  $output = & python $script --output-dir $OutputDir 2>&1
  $code = $LASTEXITCODE
  foreach ($line in $output) {
    Write-Log $line
  }
  if ($code -ne 0) {
    throw "同步回归测试失败，退出码: $code"
  }
  Write-Log '同步回归测试全部通过'
  Write-Log ("报告目录: {0}" -f $OutputDir)
  exit 0
} catch {
  Write-Log ("同步回归测试失败: {0}" -f $_.Exception.Message)
  exit 1
}
