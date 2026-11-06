$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot '..\..\scripts\start-android-dev.ps1'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw "Startup script parse failed: $($errors[0])" }
$definition = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Wait-ForTargetAvd' }, $true)
Invoke-Expression $definition.Extent.Text
function Get-Process { param([int]$Id) return [pscustomobject]@{ Id = $Id } }
function Get-Date { $script:now = $script:now.AddSeconds(50); return $script:now }
function Start-Sleep { param($Seconds) }
function Set-Stage { param($Name) $script:stage = $Name }
function Write-Stage { param($Message) }
function Get-TargetAvdSerial { if ($script:connected) { return 'emulator-5554' }; return $null }
function Get-AndroidSystemReadiness { param($Serial) return [pscustomobject]@{ Ready = $true; Summary = 'stable' } }
function Test-SnapshotLoadFailure { return $false }
function Repair-TargetAvdTransport { param($EmulatorPid) $script:repairCalled = $true; throw 'adb_transport_unavailable: target transport recovery exhausted' }
$script:connected = $true; $script:now = [datetime]'2026-11-07'; $script:systemStableSamples = 0
$script:transportPorts = @('5554=missing', '5555=missing')
$serial = Wait-ForTargetAvd -EmulatorPid 1234
if ($serial -ne 'emulator-5554' -or $script:systemStableSamples -ne 2) { throw 'Blank TCP State blocked a ready ADB target' }
$script:connected = $false; $script:now = [datetime]'2026-11-07'; $script:repairCalled = $false
try { [void](Wait-ForTargetAvd -EmulatorPid 1234); throw 'Missing ADB target was accepted' }
catch { if ($_.Exception.Message -notmatch '^adb_transport_unavailable:' -or -not $script:repairCalled) { throw } }
Write-Host 'Android transport readiness regression passed.'
$reverseDefinition = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-AndroidReverse' }, $true)
Invoke-Expression $reverseDefinition.Extent.Text
function MockAdb { $global:LASTEXITCODE = 0; if ($script:mappingPresent) { 'host-18 tcp:8000 tcp:8000' } }
$script:adb = 'MockAdb'; $script:mappingPresent = $true
Assert-AndroidReverse 'emulator-5554'
if (-not $script:reverseVerified) { throw 'Present reverse mapping was rejected' }
$script:mappingPresent = $false
try { Assert-AndroidReverse 'emulator-5554'; throw 'Missing reverse mapping was accepted' }
catch { if ($_.Exception.Message -notmatch '^adb_reverse_missing:' -or $script:reverseVerified) { throw } }
Write-Host 'Android reverse verification regression passed.'
