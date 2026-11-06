$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$scriptPath = Join-Path $root 'scripts\start-local-process.ps1'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'startup script parse failed' }
foreach ($name in @('Test-ProjectProcess', 'Test-TcpBindAvailable')) {
    $node = $ast.Find({ param($candidate) $candidate -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $candidate.Name -eq $name }, $true)
    if (-not $node) { throw "missing $name" }
    . ([scriptblock]::Create($node.Extent.Text))
}
function Get-CimInstance {
    [CmdletBinding()] param([Parameter(Position=0)][string]$ClassName, [string]$Filter)
    $id = [int]([regex]::Match($Filter, '\d+').Value)
    $base = if ($id -eq 8) { 'D:\OtherProject' } else { $root }
    if ($id -eq 9) { return [pscustomobject]@{ CommandLine = 'node unrelated.js' } }
    return [pscustomobject]@{ CommandLine = "python -m uvicorn server.server:app --app-dir `"$base`" --host 0.0.0.0 --port 8000" }
}
if (-not (Test-ProjectProcess -ProcessId 7 -ProcessName Server)) { throw 'project server rejected' }
if (Test-ProjectProcess -ProcessId 8 -ProcessName Server) { throw 'foreign workspace accepted' }
if (Test-ProjectProcess -ProcessId 9 -ProcessName Server) { throw 'unrelated process accepted' }
function Invoke-Preflight([int]$ServerPort, [int]$UiPort) {
    $start = [Diagnostics.ProcessStartInfo]::new('powershell.exe')
    $path = Join-Path $root 'scripts\wait-local-readiness.ps1'
    $start.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$path`" -ServerUrl http://127.0.0.1:$ServerPort/ping -UiUrl http://127.0.0.1:$UiPort/ -RequirePortsFree"
    $start.UseShellExecute = $false; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::Start($start)
    $stdout = $process.StandardOutput.ReadToEnd(); $stderr = $process.StandardError.ReadToEnd(); $process.WaitForExit()
    return @{ Exit = $process.ExitCode; Output = "$stdout $stderr" }
}
$holder = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$holder.Start()
$port = ([Net.IPEndPoint]$holder.LocalEndpoint).Port
try {
    if (Test-TcpBindAvailable -Port $port -Address ([Net.IPAddress]::Loopback)) { throw 'occupied port reported free' }
    $ui = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0); $ui.Start()
    $uiPort = ([Net.IPEndPoint]$ui.LocalEndpoint).Port; $ui.Stop()
    $result = Invoke-Preflight -ServerPort $port -UiPort $uiPort
    if ($result.Exit -ne 3 -or $result.Output -notmatch 'already in use') { throw 'occupied preflight passed' }
} finally { $holder.Stop() }
if (-not (Test-TcpBindAvailable -Port $port -Address ([Net.IPAddress]::Loopback))) { throw 'released port reported occupied' }
$result = Invoke-Preflight -ServerPort $port -UiPort $uiPort
if ($result.Exit -ne 0) { throw "free preflight failed: $($result.Output)" }
Write-Output 'local startup port tests passed'
