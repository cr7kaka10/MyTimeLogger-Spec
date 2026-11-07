$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5) { throw '请使用 Windows PowerShell 5.1 运行此测试' }
$probeDir = Join-Path $env:TEMP ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $probeDir | Out-Null
$env:MTL_AUTH_MARKER = Join-Path $probeDir 'authorized'
$env:MTL_AUTH_LOG = Join-Path $probeDir 'calls'
$mockSource = @'
using System;
using System.IO;
class Program {
  static int Main(string[] args) {
    bool key = Array.Exists(args, x => x == "BatchMode=yes");
    File.AppendAllText(Environment.GetEnvironmentVariable("MTL_AUTH_LOG"), key ? "key\n" : "password\n");
    if (key) {
      if (File.Exists(Environment.GetEnvironmentVariable("MTL_AUTH_MARKER"))) return 0;
      Console.Error.WriteLine("Permission denied (publickey,password)."); return 255;
    }
    string command = args[args.Length - 1];
    if (!command.Contains("ssh-ed25519") || !command.Contains("echo >>") || Environment.GetEnvironmentVariable("MTL_AUTH_FAIL") == "1") {
      Console.Error.WriteLine("Permission denied, please try again."); return 255;
    }
    File.WriteAllText(Environment.GetEnvironmentVariable("MTL_AUTH_MARKER"), command); return 0;
  }
}
'@
Add-Type -TypeDefinition $mockSource -OutputAssembly (Join-Path $probeDir 'ssh.exe') -OutputType ConsoleApplication
$env:PATH = "$probeDir;$env:PATH"
$identityPath = Join-Path $probeDir 'migration-key'
$SshPort = 22
Set-Content -LiteralPath "$identityPath.pub" -Value 'ssh-ed25519 AAAATEST migration-test' -Encoding ascii
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\migrate-server.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw '迁移脚本无法解析' }
foreach ($name in @('Test-KeyAccess', 'Ensure-KeyAccess')) {
  $definition = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)[0]
  Invoke-Expression $definition.Extent.Text
}
Ensure-KeyAccess 'root@example' '测试服务器'
Ensure-KeyAccess 'root@example' '测试服务器'
if ((Get-Content $env:MTL_AUTH_LOG | Where-Object { $_ -eq 'password' }).Count -ne 1) { throw '密码安装不止一次' }
$env:MTL_AUTH_MARKER = Join-Path $probeDir 'bad-authorized'
$env:MTL_AUTH_FAIL = '1'
try { Ensure-KeyAccess 'root@example' '测试服务器'; throw '错误密码未中止' }
catch { if ($_.Exception.Message -notmatch '密码错误或 SSH 登录失败') { throw } }
Write-Host 'PASS: Windows PowerShell 5.1 key probe, one password, and wrong-password hint'
