param(
    [switch]$PreflightOnly,
    [switch]$DryRun,
    [ValidateSet('stale_runtime', 'complete_snapshot', 'active_lock', 'unknown_lock', 'avd_missing', 'boot_timeout', 'transport_unavailable', 'transport_ready', 'window_service_pending', 'bootanim_running', 'systemui_unstable', 'build_failure', 'active_start', 'surface_delayed', 'activity_recovered', 'activity_not_foreground', 'activity_window_not_visible', 'input_ready', 'input_no_window', 'input_recovered', 'input_reboot_recovered', 'input_recovery_failed')]
    [string]$TestScenario
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$avdName = 'aTimeLogger_Extraction_API35'
$targetSerial = 'emulator-5554'
$serverUrl = 'http://127.0.0.1:8000'
$gradleWrapper = Join-Path $root 'ui\android\gradlew.bat'
$windowBoundsHelper = Join-Path $PSScriptRoot 'ensure-window-visible.ps1'
$androidSdk = @($env:ANDROID_SDK_ROOT, $env:ANDROID_HOME, (Join-Path $env:LOCALAPPDATA 'Android\Sdk')) |
    Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
$runStamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('yyyyMMdd-HHmmss')
$logDirectory = Join-Path $root 'tests\runtime\startup-logs'
$script:logPath = Join-Path $logDirectory "android-$runStamp.log"
$script:summaryPath = Join-Path $logDirectory "android-$runStamp.summary.json"
$script:stage = 'initialize'
$script:serial = ''
$script:archivePaths = @()
$script:errorCategory = ''
$script:errorReason = ''
$script:recoveryActions = @()
$script:adbPath = ''
$script:transportPorts = @()
$script:inputReady = $false
$script:inputDiagnostics = 'not_checked'
$script:bootCompleted = ''
$script:bootAnimation = ''
$script:systemWindowReady = $false
$script:systemStableSamples = 0
$script:systemDiagnostics = 'not_checked'
$script:activityForeground = $false
$script:activitySurface = $false
$script:appCrashed = $false
$script:appRecoveryCount = 0
$script:activityDiagnostics = 'not_checked'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

function Write-Stage([string]$message) {
    $line = "[$([DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('yyyy-MM-dd HH:mm:ss'))] [$script:stage] $message"
    Write-Host "[android] $line"
    Add-Content -LiteralPath $script:logPath -Value $line
}

function Set-Stage([string]$name) {
    $script:stage = $name
    Write-Stage 'started'
}

function Write-StartupSummary([int]$ExitCode) {
    $result = if ($ExitCode -eq 0) { 'success' } else { 'failed' }
    [pscustomobject]@{
        timestamp_beijing = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('yyyy-MM-dd HH:mm:ss')
        result = $result; stage = $script:stage; error_category = $script:errorCategory
        error_reason = $script:errorReason; recovery_actions = @($script:recoveryActions)
        avd = $avdName; serial = $script:serial; exit_code = $ExitCode
        archive_paths = @($script:archivePaths); log_path = $script:logPath
        adb_path = $script:adbPath; transport_ports = @($script:transportPorts)
        input_ready = [bool]$script:inputReady; input_diagnostics = $script:inputDiagnostics
        boot_completed = $script:bootCompleted; boot_animation = $script:bootAnimation
        system_window_ready = [bool]$script:systemWindowReady
        system_stable_samples = [int]$script:systemStableSamples; system_diagnostics = $script:systemDiagnostics
        activity_foreground = [bool]$script:activityForeground; activity_surface = [bool]$script:activitySurface
        app_crashed = [bool]$script:appCrashed; app_recovery_count = [int]$script:appRecoveryCount
        activity_diagnostics = $script:activityDiagnostics
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $script:summaryPath -Encoding utf8
    Write-Host "[android] Summary: $script:summaryPath ($result/$script:stage)"
}

function Get-StartupErrorCategory([System.Exception]$Error) {
    $message = [string]$Error.Message
    if ($message -match 'adb_transport_unavailable') { return 'adb_transport_unavailable' }
    if ($message -match 'system_window_unstable') { return 'system_window_unstable' }
    if ($message -match 'Timed out') { return 'boot_timeout' }
    if ($message -match 'emulator_exited') { return 'emulator_exited' }
    if ($message -match 'runtime_state') { return 'runtime_state_invalid' }
    if ($message -match 'Preflight') { return 'preflight_failed' }
    if ($message -match 'install') { return 'install_failed' }
    if ($message -match 'app_crashed') { return 'app_crashed' }
    if ($message -match 'activity_not_foreground') { return 'activity_not_foreground' }
    if ($message -match 'activity_window_not_visible') { return 'activity_window_not_visible' }
    if ($message -match 'input_focus_unavailable') { return 'input_focus_unavailable' }
    return 'stage_failed'
}

function Remove-LegacyFastbootDuplicates([string]$AvdPath, [string]$ArchiveRoot) {
    $configPath = Join-Path $AvdPath 'config.ini'
    if (-not (Test-Path -LiteralPath $configPath)) { throw 'runtime_state_config_missing' }
    $seen = @{}; $changed = $false
    $content = foreach ($line in (Get-Content -LiteralPath $configPath)) {
        if ($line -match '^\s*(fastboot\.force(?:ColdBoot|FastBoot))\s*=') {
            if ($seen[$matches[1]]) { $changed = $true; continue }
            $seen[$matches[1]] = $true
        }
        $line
    }
    if ($changed) {
        Copy-Item -LiteralPath $configPath -Destination (Join-Path $ArchiveRoot 'config.ini.before-fastboot-dedupe') -ErrorAction Stop
        [System.IO.File]::WriteAllLines($configPath, [string[]]$content, [System.Text.UTF8Encoding]::new($false))
        $script:recoveryActions += 'dedupe_legacy_fastboot_config'
    }
}

function Invoke-ControlledDryRun([string]$Scenario) {
    $script:adbPath = 'dry-run-sdk\platform-tools\adb.exe'
    $outcomes = @{
        stale_runtime = @{ stage = 'runtime_state'; ok = $true; archive = $true; action = 'archive_confirmed_runtime' }
        complete_snapshot = @{ stage = 'runtime_state'; ok = $true; action = 'fast_boot_complete_snapshot' }
        active_lock = @{ stage = 'runtime_state'; ok = $false; error = 'runtime_state_invalid'; reason = 'runtime_state_active_lock' }
        unknown_lock = @{ stage = 'runtime_state'; ok = $false; error = 'runtime_state_invalid'; reason = 'runtime_state_unknown_lock' }
        avd_missing = @{ stage = 'preflight'; ok = $false; error = 'preflight_failed'; reason = 'avd_missing' }
        boot_timeout = @{ stage = 'boot_wait'; ok = $false; error = 'boot_timeout'; reason = 'boot_timeout' }
        transport_unavailable = @{ stage = 'transport_wait'; ok = $false; error = 'adb_transport_unavailable'; reason = 'adb_transport_unavailable: 5554=missing,5555=missing' }
        transport_ready = @{ stage = 'boot_wait'; ok = $true; action = 'adb_transport_ready'; serial = $targetSerial }
        window_service_pending = @{ stage = 'boot_wait'; ok = $true; serial = $targetSerial; system_diagnostic = 'window_service_pending: Can''t find service: window' }
        bootanim_running = @{ stage = 'boot_wait'; ok = $false; error = 'system_window_unstable'; reason = 'system_window_unstable: boot animation running'; boot = '1'; bootanim = 'running'; stable = 0 }
        systemui_unstable = @{ stage = 'boot_wait'; ok = $false; error = 'system_window_unstable'; reason = 'system_window_unstable: system window not drawn; app_crashed=False'; boot = '1'; bootanim = 'stopped'; stable = 0; crashed = $false }
        build_failure = @{ stage = 'web_build'; ok = $false; error = 'stage_failed'; reason = 'build_failure' }
        active_start = @{ stage = 'foreground_request'; ok = $true; serial = $targetSerial }
        surface_delayed = @{ stage = 'activity_readiness'; ok = $true; foreground = $true; surface = $true; input_ready = $true; recoveries = 0; diagnostic = 'foreground=True;surface=True;input=True;crashed=False' }
        activity_recovered = @{ stage = 'activity_readiness'; ok = $true; action = 'recover_target_app_input'; foreground = $true; surface = $true; input_ready = $true; recoveries = 1; diagnostic = 'foreground=True;surface=True;input=True;crashed=False' }
        activity_not_foreground = @{ stage = 'activity_start'; ok = $false; error = 'activity_not_foreground'; reason = 'activity_not_foreground: expected MainActivity to be foreground' }
        activity_window_not_visible = @{ stage = 'activity_start'; ok = $false; error = 'activity_window_not_visible'; reason = 'activity_window_not_visible: expected MainActivity surface to be shown' }
        input_ready = @{ stage = 'input_readiness'; ok = $true; input_ready = $true; action = 'input_focus_ready'; diagnostic = 'application=True;window=True;connection=True;no_window=False' }
        input_no_window = @{ stage = 'input_readiness'; ok = $false; input_ready = $false; error = 'input_focus_unavailable'; reason = 'input_focus_unavailable: FocusedWindows none'; action = 'recover_target_app_input'; diagnostic = 'application=True;window=False;connection=True;no_window=True' }
        input_recovered = @{ stage = 'input_readiness'; ok = $true; input_ready = $true; action = 'recover_target_app_input'; diagnostic = 'application=True;window=True;connection=True;no_window=False' }
        input_reboot_recovered = @{ stage = 'input_readiness'; ok = $true; input_ready = $true; actions = @('recover_target_app_input', 'reboot_target_avd_input'); diagnostic = 'application=True;window=True;connection=True;no_window=False' }
        input_recovery_failed = @{ stage = 'input_readiness'; ok = $false; input_ready = $false; error = 'input_focus_unavailable'; reason = 'input_focus_unavailable: recovery exhausted'; actions = @('recover_target_app_input', 'reboot_target_avd_input'); diagnostic = 'application=True;window=False;connection=True;no_window=True' }
    }
    $outcome = $outcomes[$Scenario]
    Set-Stage $outcome.stage
    if ($outcome.archive) { $script:archivePaths = @('dry-run-runtime-recovery') }
    if ($outcome.actions) { $script:recoveryActions = @($outcome.actions) }
    elseif ($outcome.action) { $script:recoveryActions = @($outcome.action) }
    if ($outcome.serial) { $script:serial = $outcome.serial }
    if ($null -ne $outcome.input_ready) { $script:inputReady = [bool]$outcome.input_ready }
    if ($outcome.diagnostic) { $script:inputDiagnostics = $outcome.diagnostic; $script:activityDiagnostics = $outcome.diagnostic }
    if ($outcome.system_diagnostic) { $script:systemDiagnostics = $outcome.system_diagnostic }
    if ($outcome.boot) { $script:bootCompleted = $outcome.boot; $script:bootAnimation = $outcome.bootanim; $script:systemStableSamples = $outcome.stable }
    if ($null -ne $outcome.foreground) { $script:activityForeground = [bool]$outcome.foreground; $script:activitySurface = [bool]$outcome.surface }
    if ($null -ne $outcome.recoveries) { $script:appRecoveryCount = [int]$outcome.recoveries }
    if ($null -ne $outcome.crashed) { $script:appCrashed = [bool]$outcome.crashed }
    if ($Scenario -eq 'transport_unavailable') { $script:transportPorts = @('5554=missing', '5555=missing') }
    if ($Scenario -eq 'transport_ready') { $script:transportPorts = @('5554=listening', '5555=listening') }
    if (-not $outcome.ok) { $script:errorCategory = $outcome.error; $script:errorReason = $outcome.reason; return $false }
    Write-Stage 'Controlled dry-run completed.'
    return $true
}

function Show-Plan {
    Write-Stage "Target AVD: $avdName"
    Write-Stage "Server URL: $serverUrl"
    Write-Stage 'Plan: preflight, reuse-or-start AVD, wait for boot, stage web, sync Capacitor, install Debug APK, configure HTTP reverse, start MainActivity.'
}

function Invoke-Preflight {
    $missing = [System.Collections.Generic.List[string]]::new()
    if (-not $androidSdk) { $missing.Add('Android SDK (set ANDROID_SDK_ROOT or ANDROID_HOME)') }
    $script:adb = if ($androidSdk) { Join-Path $androidSdk 'platform-tools\adb.exe' }
    $script:emulator = if ($androidSdk) { Join-Path $androidSdk 'emulator\emulator.exe' }
    if (-not (Test-Path $script:adb)) { $missing.Add('Android SDK platform-tools\\adb.exe') }
    if (-not (Test-Path $script:emulator)) { $missing.Add('Android SDK emulator\\emulator.exe') }
    $jdkHomes = @($env:JAVA_HOME, (Join-Path $env:ProgramFiles 'Android\Android Studio\jbr')) |
        Where-Object { $_ -and (Test-Path (Join-Path $_ 'bin\javac.exe')) }
    $script:jdkHome = $jdkHomes | Where-Object {
        (& (Join-Path $_ 'bin\javac.exe') -version 2>&1 | Select-Object -First 1) -match '^javac 21\.'
    } | Select-Object -First 1
    if (-not $script:jdkHome) { $missing.Add('JDK 21 (set JAVA_HOME or install Android Studio JBR)') }
    if (-not (Test-Path $gradleWrapper)) { $missing.Add('ui\\android\\gradlew.bat') }
    if (Test-Path $script:emulator) {
        $avds = & $script:emulator -list-avds
        if ($LASTEXITCODE -ne 0 -or $avdName -notin $avds) { $missing.Add("AVD $avdName") }
    }
    if (Test-Path $script:adb) {
        $script:adbPath = $script:adb
        & $script:adb start-server
        if ($LASTEXITCODE -ne 0) { $missing.Add('Android SDK adb server') }
    }
    if ($missing.Count) {
        $missing | ForEach-Object { [Console]::Error.WriteLine("[android] Missing: $_") }
        return $false
    }
    $env:ANDROID_HOME = $androidSdk
    $env:ANDROID_SDK_ROOT = $androidSdk
    $env:JAVA_HOME = $script:jdkHome
    $env:PATH = "$(Join-Path $script:jdkHome 'bin');$env:PATH"
    Write-Stage 'Preflight passed.'
    return $true
}

function Get-TargetAvdSerial {
    $devices = & $script:adb devices
    $script:transportPorts = @(5554, 5555 | ForEach-Object {
        if (Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue) { "$_=listening" } else { "$_=missing" }
    })
    foreach ($line in $devices | Select-Object -Skip 1) {
        if ($line -match ('^' + [regex]::Escape($targetSerial) + '\s+device$') -and (Get-TargetEmulatorPid)) {
            return $targetSerial
        }
    }
    return $null
}

function Repair-TargetAvdRuntimeState {
    $avdPath = Join-Path $env:USERPROFILE ".android\avd\$avdName.avd"
    $lockPath = Join-Path $avdPath 'hardware-qemu.ini.lock'
    $snapshotPath = Join-Path $avdPath 'snapshots\default_boot'
    if (-not (Test-Path -LiteralPath $avdPath)) { throw 'runtime_state_avd_missing' }
    if (Get-TargetEmulatorPid) { Write-Stage 'Target AVD process exists; runtime files left untouched.'; return $false }
    $archiveTargets = @()
    $coldStart = $false
    if (Test-Path -LiteralPath $lockPath) {
        $pidPath = Join-Path $lockPath 'pid'
        if (-not (Test-Path -LiteralPath $pidPath)) { throw 'runtime_state_unknown_lock' }
        $rawPid = (Get-Content -LiteralPath $pidPath -Raw).Trim()
        if ($rawPid -notmatch '^\d+$') { throw 'runtime_state_unknown_lock' }
        if (Get-Process -Id ([int]$rawPid) -ErrorAction SilentlyContinue) { throw 'runtime_state_active_lock' }
        $archiveTargets += $lockPath
    }
    if (Test-Path -LiteralPath $snapshotPath) {
        $complete = (Test-Path -LiteralPath (Join-Path $snapshotPath 'ram.img')) -and
            (Test-Path -LiteralPath (Join-Path $snapshotPath 'snapshot.pb'))
        if (-not $complete) { $archiveTargets += $snapshotPath; $coldStart = $true }
    }
    if ($archiveTargets.Count) {
        $archiveRoot = Join-Path $avdPath "runtime-recovery-$runStamp"
        New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
        foreach ($target in $archiveTargets) { Move-Item -LiteralPath $target -Destination $archiveRoot -ErrorAction Stop }
        if ($coldStart) { Remove-LegacyFastbootDuplicates $avdPath $archiveRoot }
        $script:archivePaths = @($archiveRoot)
        $script:recoveryActions = @('archive_confirmed_runtime')
        Write-Stage "Archived confirmed target AVD runtime state; cold start=$coldStart."
        return $coldStart
    }
    $script:recoveryActions = @('fast_boot_complete_snapshot')
    Write-Stage 'Target AVD runtime state is safe for normal startup.'
    return $false
}

function Start-TargetAvd([bool]$ColdStart = $false) {
    $serial = Get-TargetAvdSerial
    if ($serial) {
        Write-Stage "Reusing target AVD: $serial"
        return Get-TargetEmulatorPid
    }
    $existingPid = Get-TargetEmulatorPid
    if ($existingPid) {
        Write-Stage "Target AVD process already exists (PID $existingPid); waiting for $targetSerial transport."
        return $existingPid
    }
    $arguments = @('-avd', $avdName, '-port', '5554')
    if ($ColdStart) { $arguments += @('-no-snapshot-load', '-no-snapshot-save') }
    $process = Start-Process -FilePath $script:emulator -ArgumentList $arguments -PassThru
    Write-Stage "Started target AVD $avdName (emulator PID $($process.Id))."
    return $process.Id
}

function Get-TargetEmulatorPid {
    $pattern = '(?i)(?:^|\s)-avd\s+(?:"?' + [regex]::Escape($avdName) + '"?)(?=\s|$)'
    $process = Get-CimInstance Win32_Process -Filter "Name = 'qemu-system-x86_64.exe'" |
        Where-Object { $_.CommandLine -match $pattern } |
        Select-Object -First 1
    return $process.ProcessId
}

function Request-TargetEmulatorForeground([int]$EmulatorPid) {
    $windowPid = Get-TargetEmulatorPid
    if (-not $windowPid) { Write-Stage "Target emulator window PID is unavailable; App startup continues."; return }
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            & $windowBoundsHelper -WindowProcessId $windowPid -Attempt $attempt
            if ($LASTEXITCODE -eq 0) { Write-Stage "Target emulator window is fully visible and foreground (PID $windowPid, attempt $attempt)."; return }
        } catch { $lastError = $_.Exception.Message }
        Start-Sleep -Milliseconds 500
    }
    Write-Stage "Unable to foreground target emulator PID $windowPid; App startup continues. $lastError"
}

function Get-BootCompleted([string]$Serial) {
    $job = Start-Job -ScriptBlock { param($Adb, $Device) & $Adb -s $Device shell getprop sys.boot_completed 2>$null } `
        -ArgumentList $script:adb, $Serial
    try {
        if (-not (Wait-Job -Job $job -Timeout 5)) { Stop-Job -Job $job; return '' }
        $value = (Receive-Job -Job $job | Select-Object -First 1) -as [string]
        if ($value) { return $value.Trim() }
        return ''
    } finally {
        Remove-Job -Job $job -Force
    }
}

function Get-AndroidSystemReadiness([string]$Serial) {
    $boot = Get-BootCompleted $Serial
    $bootAnimation = ((& $script:adb -s $Serial shell getprop init.svc.bootanim 2>$null) | Select-Object -First 1) -as [string]
    if ($LASTEXITCODE -ne 0) { throw 'adb_transport_unavailable: boot animation query failed' }
    try {
        $displays = (& $script:adb -s $Serial shell dumpsys window displays 2>&1) -join "`n"
        $displayExit = $LASTEXITCODE
        $windows = (& $script:adb -s $Serial shell dumpsys window windows 2>&1) -join "`n"
        $windowExit = $LASTEXITCODE
    } catch {
        $displays = ''; $windows = ''; $displayExit = 0; $windowExit = 0
        $windowFailure = [string]$_.Exception.Message
    }
    $windowOutput = "$displays`n$windows`n$windowFailure"
    if ($windowOutput -match "Can't find service: window") {
        $reason = "window_service_pending: $($matches[0])"
        $script:bootCompleted = $boot; $script:bootAnimation = if ($bootAnimation) { $bootAnimation.Trim() } else { '' }
        $script:systemWindowReady = $false; $script:systemDiagnostics = $reason
        return [pscustomobject]@{ Ready = $false; Summary = $reason }
    }
    if ($displayExit -ne 0 -or $windowExit -ne 0) { throw 'adb_transport_unavailable: window query failed' }
    $focus = [regex]::Match($displays, 'mCurrentFocus=Window\{([^\s]+)\s+u\d+\s+([^}]+)\}')
    $focusWindow = if ($focus.Success) {
        [regex]::Match($windows, ('(?s)Window #\d+ Window\{' + [regex]::Escape($focus.Groups[1].Value) + ' .*?(?=\r?\n\s*Window #|\z)')).Value
    } else { '' }
    $windowReady = $focus.Success -and $focusWindow -match 'Surface:\s+shown=true'
    $anrWindows = [regex]::Matches($windows, '(?s)Window #\d+ Window\{[^\r\n]*Application Not Responding: com\.android\.systemui\}:(.*?)(?=\r?\n\s*Window #|\z)')
    $visibleSystemAnr = @($anrWindows | Where-Object { $_.Value -match 'Surface:\s+shown=true' }).Count -gt 0
    $animation = if ($bootAnimation) { $bootAnimation.Trim() } else { '' }
    $ready = $boot -eq '1' -and $animation -eq 'stopped' -and $windowReady -and -not $visibleSystemAnr
    $reason = "boot=$boot;bootanim=$animation;focus=$($focus.Groups[2].Value);window=$windowReady;systemui_anr=$visibleSystemAnr"
    $script:bootCompleted = $boot; $script:bootAnimation = $animation
    $script:systemWindowReady = [bool]$windowReady; $script:systemDiagnostics = $reason
    return [pscustomobject]@{ Ready = $ready; Summary = $reason }
}

function Wait-ForTargetAvd([int]$EmulatorPid, [int]$TimeoutSeconds = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $transportDeadline = (Get-Date).AddSeconds(45)
    do {
        if (-not (Get-Process -Id $EmulatorPid -ErrorAction SilentlyContinue)) { throw 'emulator_exited_before_boot' }
        $serial = Get-TargetAvdSerial
        $portsReady = ($script:transportPorts -contains '5554=listening') -and ($script:transportPorts -contains '5555=listening')
        if ($portsReady -and $serial) {
            $state = Get-AndroidSystemReadiness $serial
            $script:systemStableSamples = if ($state.Ready) { $script:systemStableSamples + 1 } else { 0 }
            Write-Stage "System readiness sample $script:systemStableSamples/2: $($state.Summary)"
            if ($script:systemStableSamples -ge 2) { Write-Stage "Target AVD system is stable: $serial"; return $serial }
        }
        if ((Get-Date) -ge $transportDeadline -and (-not $portsReady -or -not $serial)) {
            Set-Stage 'transport_wait'
            throw "adb_transport_unavailable: $($script:transportPorts -join ','); target=$targetSerial"
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if ($script:bootCompleted -ne '1') { throw "Timed out after $TimeoutSeconds seconds waiting for booted AVD $avdName." }
    throw "system_window_unstable: $script:systemDiagnostics"
}

function Invoke-Checked([string]$Stage, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Stage failed (exit $LASTEXITCODE)." }
}

function Invoke-AndroidWebBuild {
    $env:VITE_MTL_DEFAULT_ENVIRONMENT = 'development'
    $env:VITE_MTL_DEVELOPMENT_SERVER_URL = $serverUrl
    Push-Location (Join-Path $root 'ui')
    try {
        Write-Stage 'Building Android web staging for development HTTP.'
        Invoke-Checked 'npm run build:android-web' { npm run build:android-web }
        Write-Stage 'Synchronizing Capacitor Android project.'
        Invoke-Checked 'npx cap sync android' { npx cap sync android }
    } finally {
        Pop-Location
    }
}

function Install-DebugApk([string]$Serial) {
    $previousSerial = $env:ANDROID_SERIAL
    $env:ANDROID_SERIAL = $Serial
    Push-Location (Join-Path $root 'ui\android')
    try {
        Write-Stage "Installing Debug APK on $Serial."
        Invoke-Checked ':app:installDebug' { & $gradleWrapper ':app:installDebug' }
    } finally {
        $env:ANDROID_SERIAL = $previousSerial
        Pop-Location
    }
}

function Start-AndroidApp([string]$Serial) {
    $reverseList = & $script:adb -s $Serial reverse --list
    if ($LASTEXITCODE -ne 0) { throw "adb reverse --list failed (exit $LASTEXITCODE)." }
    if ($reverseList -match 'tcp:18010') {
        Write-Stage 'Removing legacy HTTP reverse tcp:18010.'
        Invoke-Checked 'adb reverse --remove tcp:18010' { & $script:adb -s $Serial reverse --remove tcp:18010 }
    } else {
        Write-Stage 'Legacy HTTP reverse tcp:18010 is already absent.'
    }
    Write-Stage 'Configuring HTTP reverse tcp:8000 -> tcp:8000.'
    Invoke-Checked 'adb reverse tcp:8000' { & $script:adb -s $Serial reverse tcp:8000 tcp:8000 }
    Write-Stage "Starting com.mytimelogger.app/.MainActivity on $Serial."
    Invoke-Checked 'adb shell am start MainActivity' {
        & $script:adb -s $Serial shell am start -W -n 'com.mytimelogger.app/.MainActivity'
    }
}

function Get-AndroidInputReadiness([string]$Serial) {
    $dump = (& $script:adb -s $Serial shell dumpsys input) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "adb dumpsys input failed (exit $LASTEXITCODE)." }
    $application = [regex]::Match($dump, '(?s)FocusedApplications:(.*?)(?=\r?\n\s*FocusedWindows:)').Groups[1].Value
    $windows = [regex]::Match($dump, '(?s)FocusedWindows:(.*?)(?=\r?\n\s*FocusRequests:)').Groups[1].Value
    $requests = [regex]::Match($dump, '(?s)FocusRequests:(.*?)(?=\r?\n\s*Pointer Capture Requested:)').Groups[1].Value
    $connection = [regex]::Match($dump, '(?m)^\s*\d+: channelName=.*com\.mytimelogger\.app.*MainActivity.*$').Value
    $appReady = $application -match 'com\.mytimelogger\.app/\.MainActivity'
    $windowReady = $windows -match 'com\.mytimelogger\.app.*MainActivity'
    $connectionReady = $connection -match 'status=NORMAL' -and $connection -match 'responsive=true'
    $noWindow = $requests -match 'NO_WINDOW'
    $summary = "application=$appReady;window=$windowReady;connection=$connectionReady;no_window=$noWindow"
    return [pscustomobject]@{ Ready = $appReady -and $windowReady -and $connectionReady -and -not $noWindow; Summary = $summary }
}

function Get-AndroidAppReadiness([string]$Serial) {
    $activities = (& $script:adb -s $Serial shell dumpsys activity activities 2>$null) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "adb dumpsys activity failed (exit $LASTEXITCODE)." }
    $windows = (& $script:adb -s $Serial shell dumpsys window windows 2>$null) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "adb dumpsys window failed (exit $LASTEXITCODE)." }
    $foreground = $activities -match '(?:topResumedActivity|mResumedActivity)=.*com\.mytimelogger\.app/\.MainActivity'
    $window = [regex]::Match($windows, '(?s)Window #\d+ Window\{[^\r\n]*com\.mytimelogger\.app/(?:com\.mytimelogger\.app\.)?MainActivity\}:(.*?)(?=\r?\n\s*Window #|\z)')
    $surface = $window.Success -and $window.Value -match 'Surface:\s+shown=true'
    $appProcessId = ((& $script:adb -s $Serial shell pidof com.mytimelogger.app 2>$null) | Select-Object -First 1) -as [string]
    $crashed = $false
    if (-not $appProcessId) {
        $exitInfo = (& $script:adb -s $Serial shell dumpsys activity exit-info com.mytimelogger.app 2>$null) -join "`n"
        $crashed = $exitInfo -match '(?i)reason=(?:CRASH|CRASH_NATIVE)|REASON_CRASH'
    }
    try { $input = Get-AndroidInputReadiness $Serial } catch { $input = [pscustomobject]@{ Ready = $false; Summary = 'query_failed' } }
    $summary = "foreground=$foreground;surface=$surface;input=$($input.Ready);crashed=$crashed"
    $script:activityForeground = [bool]$foreground; $script:activitySurface = [bool]$surface
    $script:inputReady = [bool]$input.Ready; $script:inputDiagnostics = $input.Summary
    $script:appCrashed = [bool]$crashed; $script:activityDiagnostics = $summary
    return [pscustomobject]@{ Ready = $foreground -and $surface -and $input.Ready -and -not $crashed; Summary = $summary }
}

function Wait-AndroidAppReady([string]$Serial, [int]$TimeoutSeconds = 12) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $state = Get-AndroidAppReadiness $Serial
        if ($state.Ready) { Write-Stage "MainActivity readiness confirmed: $($state.Summary)"; return $true }
        if ($script:appCrashed) { return $false }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    Write-Stage "MainActivity readiness timed out: $script:activityDiagnostics"
    return $false
}

function Get-AndroidAppFailureCategory {
    if ($script:appCrashed) { return 'app_crashed' }
    if (-not $script:activityForeground) { return 'activity_not_foreground' }
    if (-not $script:activitySurface) { return 'activity_window_not_visible' }
    return 'input_focus_unavailable'
}

function Wait-AndroidInputReady([string]$Serial, [int]$TimeoutSeconds = 8) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $state = Get-AndroidInputReadiness $Serial
            $script:inputDiagnostics = $state.Summary
            if ($state.Ready) { $script:inputReady = $true; return $true }
        } catch { $script:inputDiagnostics = "query_failed=$($_.Exception.GetType().Name)" }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    $script:inputReady = $false
    return $false
}

function Repair-AndroidAppInput([string]$Serial) {
    Write-Stage "Recovering input focus for target App only on $Serial."
    Invoke-Checked 'adb shell am force-stop target App' {
        & $script:adb -s $Serial shell am force-stop com.mytimelogger.app
    }
    Start-Sleep -Milliseconds 300
    Start-AndroidApp $Serial
}

function Restart-TargetAvdInput([string]$Serial, [int]$EmulatorPid) {
    Write-Stage "Soft-rebooting target AVD once to recover stuck system input on $Serial."
    & $script:adb -s $Serial shell reboot
    $rebootExit = $LASTEXITCODE
    if ($rebootExit -ne 0) { Write-Stage "adb reboot disconnected transport with exit $rebootExit; waiting for the target AVD to return." }
    $reconnectedSerial = Wait-ForTargetAvd -EmulatorPid $EmulatorPid -TimeoutSeconds 90
    if ($reconnectedSerial -ne $Serial) { throw "adb_transport_unavailable: expected $Serial after input recovery" }
    Start-AndroidApp $reconnectedSerial
    Request-TargetEmulatorForeground $EmulatorPid
}

$exitCode = 1
try {
    Set-Stage 'plan'; Show-Plan
    if ($DryRun) {
        if ($TestScenario) { if (Invoke-ControlledDryRun $TestScenario) { $exitCode = 0 } }
        else { Set-Stage 'dry_run'; Write-Stage 'Dry-run complete; no process was started and no device was accessed.'; $exitCode = 0 }
    } else {
        Set-Stage 'preflight'
        if (-not (Invoke-Preflight)) { $script:errorCategory = 'preflight_failed' }
        elseif ($PreflightOnly) { $exitCode = 0 }
        else {
            Set-Stage 'runtime_state'; $coldStart = Repair-TargetAvdRuntimeState
            Set-Stage 'avd_acquisition'; $emulatorPid = Start-TargetAvd $coldStart
            Set-Stage 'boot_wait'; $serial = Wait-ForTargetAvd -EmulatorPid $emulatorPid; $script:serial = $serial
            Set-Stage 'foreground_boot'; Request-TargetEmulatorForeground $emulatorPid
            Set-Stage 'web_build'; Invoke-AndroidWebBuild
            Set-Stage 'apk_install'; Install-DebugApk $serial
            Set-Stage 'activity_start'; Start-AndroidApp $serial
            Set-Stage 'activity_readiness'
            $appReady = Wait-AndroidAppReady $serial
            if (-not $appReady -and $script:appRecoveryCount -lt 1) {
                $script:recoveryActions += 'recover_target_app_input'
                $script:appRecoveryCount++
                Repair-AndroidAppInput $serial
                $appReady = Wait-AndroidAppReady $serial
            }
            if (-not $appReady) {
                $failure = Get-AndroidAppFailureCategory
                if ($failure -eq 'input_focus_unavailable') {
                    $script:recoveryActions += 'reboot_target_avd_input'
                    Restart-TargetAvdInput -Serial $serial -EmulatorPid $emulatorPid
                    $appReady = Wait-AndroidAppReady $serial
                }
                if (-not $appReady) { $failure = Get-AndroidAppFailureCategory; throw "${failure}: $script:activityDiagnostics" }
            }
            Set-Stage 'foreground_request'; Request-TargetEmulatorForeground $emulatorPid
            Write-Stage "Android development client is ready on $serial."
            $exitCode = 0
        }
    }
} catch {
    $script:errorCategory = Get-StartupErrorCategory $_.Exception
    $script:errorReason = ([string]$_.Exception.Message).Replace("`r", ' ').Replace("`n", ' ')
    [Console]::Error.WriteLine("[android] Startup failed at stage $script:stage ($script:errorCategory): $script:errorReason")
} finally {
    Write-StartupSummary $exitCode
}
exit $exitCode
