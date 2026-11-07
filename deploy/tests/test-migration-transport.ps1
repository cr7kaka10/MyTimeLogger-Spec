$ErrorActionPreference = 'Stop'
$probeDir = Join-Path $env:TEMP 'mtl-migration-transport-test'
New-Item -ItemType Directory -Force -Path $probeDir | Out-Null
$env:MTL_MOCK_STORE = $probeDir
$mockExe = Join-Path $probeDir "ssh-probe-$PID.exe"
$mockSource = @'
using System;
using System.IO;
class Program {
    static int Main(string[] args) {
        if (Environment.GetEnvironmentVariable("MTL_MOCK_FAIL") == "1") return 9;
        string command = args[args.Length - 1];
        bool upload = command.StartsWith("cat > ");
        if (!upload && !command.StartsWith("cat ")) return 8;
        string remote = command.Substring(upload ? 6 : 4);
        string path = Path.Combine(Environment.GetEnvironmentVariable("MTL_MOCK_STORE"), Path.GetFileName(remote));
        if (upload) { using (var file = File.Create(path)) Console.OpenStandardInput().CopyTo(file); }
        else { using (var file = File.OpenRead(path)) file.CopyTo(Console.OpenStandardOutput()); }
        return 0;
    }
}
'@
Add-Type -TypeDefinition $mockSource -OutputAssembly $mockExe -OutputType ConsoleApplication
function Get-Command($Name) {
    if ($Name -eq 'ssh') { return [pscustomobject]@{ Source = $mockExe } }
    Microsoft.PowerShell.Core\Get-Command $Name
}
function Invoke-Remote([string]$server, [string]$command) {
    if ($server -ne 'root@example' -or $command -ne 'df -Pk /mock') { throw '远端空间检查参数错误' }
    $available = if ($env:MTL_MOCK_LOW_SPACE -eq '1') { 1 } else { 99000 }
    return "Filesystem 1024-blocks Used Available Capacity Mounted on`n/dev/mock 100000 1000 $available 1% /mock"
}
$scriptPath = Join-Path $PSScriptRoot '..\migrate-server.ps1'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw '迁移脚本无法解析' }
foreach ($name in @('Assert-RemoteSpace', 'Invoke-BinaryTransfer', 'Copy-ToRemote', 'Copy-FromRemote')) {
    $definition = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)[0]
    Invoke-Expression $definition.Extent.Text
}
$identityPath = Join-Path $probeDir 'unused-key'
$SshPort = 22
$sourceFile = Join-Path $probeDir 'source.bin'
$roundtripFile = Join-Path $probeDir 'roundtrip.bin'
$data = New-Object byte[] 262144
for ($i = 0; $i -lt $data.Length; $i++) { $data[$i] = [byte]($i % 256) }
[IO.File]::WriteAllBytes($sourceFile, $data)
Copy-ToRemote $sourceFile 'root@example' '/mock/remote.bin'
Copy-FromRemote 'root@example' '/mock/remote.bin' $roundtripFile
if ((Get-FileHash $sourceFile).Hash -ne (Get-FileHash $roundtripFile).Hash) { throw '二进制传输哈希不一致' }
$env:MTL_MOCK_FAIL = '1'
try { Copy-ToRemote $sourceFile 'root@example' '/mock/fail.bin'; throw '连接失败没有被检测' }
catch { if ($_.Exception.Message -eq '连接失败没有被检测') { throw } }
$env:MTL_MOCK_FAIL = '0'
$env:MTL_MOCK_LOW_SPACE = '1'
try { Copy-ToRemote $sourceFile 'root@example' '/mock/low-space.bin'; throw '磁盘不足没有被检测' }
catch { if ($_.Exception.Message -eq '磁盘不足没有被检测') { throw } }
Write-Host 'PASS: SSH binary roundtrip, failed upload, and low space'
