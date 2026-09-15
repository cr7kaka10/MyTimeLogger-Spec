param([Parameter(Mandatory=$true)][string]$Serial, [Parameter(Mandatory=$true)][string]$AppApk, [Parameter(Mandatory=$true)][string]$TestApk)
$runner = 'com.mytimelogger.app.test/androidx.test.runner.AndroidJUnitRunner'
$class = 'com.mytimelogger.app.SecureStorageLifecycleTest#phaseContract'
function Invoke-Adb([string[]]$Command) { & adb -s $Serial @Command; if ($LASTEXITCODE -ne 0) { throw "adb_failed:$($Command -join ' ')" } }
function Invoke-Phase([string]$Phase) { Invoke-Adb @('shell','am','instrument','-w','-e','class',$class,'-e','phase',$Phase,$runner) }
Invoke-Adb @('install','-r',$AppApk)
Invoke-Adb @('install','-r',$TestApk)
Invoke-Phase 'seed'
Start-Sleep -Seconds 1
Invoke-Adb @('shell','am','force-stop','com.mytimelogger.app'); Invoke-Phase 'persist'
Read-Host '请锁屏并解锁测试设备，然后按 Enter 继续'
Invoke-Phase 'persist'
Invoke-Adb @('uninstall','com.mytimelogger.app')
Invoke-Adb @('install','-r',$AppApk); Invoke-Adb @('install','-r',$TestApk)
Invoke-Phase 'fresh_install'
