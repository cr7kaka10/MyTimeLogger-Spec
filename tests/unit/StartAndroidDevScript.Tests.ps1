$scriptPath = Join-Path $PSScriptRoot '..\..\scripts\start-android-dev.ps1'

Describe 'start-android-dev terminal summaries' {
    $cases = @(
        @{ name = 'stale runtime recovery'; scenario = 'stale_runtime'; code = 0; stage = 'runtime_state'; result = 'success'; error = ''; action = 'archive_confirmed_runtime' },
        @{ name = 'complete snapshot'; scenario = 'complete_snapshot'; code = 0; stage = 'runtime_state'; result = 'success'; error = ''; action = 'fast_boot_complete_snapshot' },
        @{ name = 'active lock'; scenario = 'active_lock'; code = 1; stage = 'runtime_state'; result = 'failed'; error = 'runtime_state_invalid'; action = '' },
        @{ name = 'unknown lock'; scenario = 'unknown_lock'; code = 1; stage = 'runtime_state'; result = 'failed'; error = 'runtime_state_invalid'; action = '' },
        @{ name = 'missing AVD'; scenario = 'avd_missing'; code = 1; stage = 'preflight'; result = 'failed'; error = 'preflight_failed' },
        @{ name = 'boot timeout'; scenario = 'boot_timeout'; code = 1; stage = 'boot_wait'; result = 'failed'; error = 'boot_timeout' },
        @{ name = 'missing adb transport'; scenario = 'transport_unavailable'; code = 1; stage = 'transport_wait'; result = 'failed'; error = 'adb_transport_unavailable'; ports = '5554=missing' },
        @{ name = 'ready adb transport'; scenario = 'transport_ready'; code = 0; stage = 'boot_wait'; result = 'success'; error = ''; action = 'adb_transport_ready'; ports = '5554=listening' },
        @{ name = 'launcher and child runtime identity'; scenario = 'target_identity_child'; code = 0; stage = 'transport_wait'; result = 'success'; error = ''; action = 'target_avd_identity_confirmed'; launcher = 25608; runtime = 13560 },
        @{ name = 'unrelated runtime identity'; scenario = 'target_identity_other'; code = 1; stage = 'transport_wait'; result = 'failed'; error = 'adb_transport_unavailable'; launcher = 25608; runtime = 22222 },
        @{ name = 'snapshot warning self recovers'; scenario = 'snapshot_self_recovered'; code = 0; stage = 'boot_wait'; result = 'success'; error = ''; action = 'snapshot_warning_self_recovered'; snapshot = 'default_boot_load_failed'; attempts = 1 },
        @{ name = 'snapshot cold recovery succeeds'; scenario = 'snapshot_cold_recovered'; code = 0; stage = 'boot_wait'; result = 'success'; error = ''; action = 'snapshot_load_failed,cold_restart_target_avd'; snapshot = 'default_boot_load_failed'; attempts = 2 },
        @{ name = 'snapshot cold recovery is exhausted'; scenario = 'snapshot_cold_exhausted'; code = 1; stage = 'transport_wait'; result = 'failed'; error = 'adb_transport_unavailable'; action = 'snapshot_load_failed,cold_restart_target_avd'; snapshot = 'default_boot_load_failed'; attempts = 2 },
        @{ name = 'emulator output is redirected'; scenario = 'emulator_output_redirected'; code = 0; stage = 'avd_acquisition'; result = 'success'; error = ''; output = $true; attempts = 1 },
        @{ name = 'window service registration pending'; scenario = 'window_service_pending'; code = 0; stage = 'boot_wait'; result = 'success'; error = ''; systemDiagnostic = 'window_service_pending' },
        @{ name = 'boot animation still running'; scenario = 'bootanim_running'; code = 1; stage = 'boot_wait'; result = 'failed'; error = 'system_window_unstable'; boot = '1'; bootanim = 'running'; stable = 0 },
        @{ name = 'unstable SystemUI sample'; scenario = 'systemui_unstable'; code = 1; stage = 'boot_wait'; result = 'failed'; error = 'system_window_unstable'; boot = '1'; bootanim = 'stopped'; stable = 0; crashed = $false },
        @{ name = 'web build failure'; scenario = 'build_failure'; code = 1; stage = 'web_build'; result = 'failed'; error = 'stage_failed' },
        @{ name = 'foreground success'; scenario = 'active_start'; code = 0; stage = 'foreground_request'; result = 'success'; error = '' },
        @{ name = 'surface appears during wait'; scenario = 'surface_delayed'; code = 0; stage = 'activity_readiness'; result = 'success'; error = ''; foreground = $true; surface = $true; inputReady = $true; recoveries = 0 },
        @{ name = 'target App recovery succeeds'; scenario = 'activity_recovered'; code = 0; stage = 'activity_readiness'; result = 'success'; error = ''; action = 'recover_target_app_input'; foreground = $true; surface = $true; inputReady = $true; recoveries = 1 },
        @{ name = 'input ready'; scenario = 'input_ready'; code = 0; stage = 'input_readiness'; result = 'success'; error = ''; inputReady = $true },
        @{ name = 'focused windows none'; scenario = 'input_no_window'; code = 1; stage = 'input_readiness'; result = 'failed'; error = 'input_focus_unavailable'; inputReady = $false },
        @{ name = 'input recovered once'; scenario = 'input_recovered'; code = 0; stage = 'input_readiness'; result = 'success'; error = ''; action = 'recover_target_app_input'; inputReady = $true },
        @{ name = 'input recovered by AVD reboot'; scenario = 'input_reboot_recovered'; code = 0; stage = 'input_readiness'; result = 'success'; error = ''; action = 'recover_target_app_input,reboot_target_avd_input'; inputReady = $true },
        @{ name = 'input recovery failed'; scenario = 'input_recovery_failed'; code = 1; stage = 'input_readiness'; result = 'failed'; error = 'input_focus_unavailable'; action = 'recover_target_app_input,reboot_target_avd_input'; inputReady = $false }
    )

    foreach ($case in $cases) {
        It "writes a sanitized summary for $($case.name)" {
            $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -DryRun -TestScenario $case.scenario 2>&1
            $LASTEXITCODE | Should Be $case.code
            $line = @($output | Where-Object { $_ -match 'Summary:' } | Select-Object -Last 1)[0]
            $summaryPath = [regex]::Match([string]$line, 'Summary: (.+) \(').Groups[1].Value
            (Test-Path -LiteralPath $summaryPath) | Should Be $true
            $summary = Get-Content -Raw -LiteralPath $summaryPath | ConvertFrom-Json
            $summary.stage | Should Be $case.stage
            $summary.result | Should Be $case.result
            $summary.error_category | Should Be $case.error
            if ($case.action) { (@($summary.recovery_actions) -join ',') | Should Be $case.action }
            if ($case.error) { $summary.error_reason | Should Not Be '' }
            if ($case.ports) { $summary.adb_path | Should Match 'platform-tools'; (@($summary.transport_ports) -contains $case.ports) | Should Be $true }
            if ($case.launcher) { $summary.launcher_emulator_pid | Should Be $case.launcher; $summary.runtime_emulator_pid | Should Be $case.runtime }
            if ($case.snapshot) { $summary.snapshot_diagnostic | Should Be $case.snapshot; $summary.emulator_start_attempts | Should Be $case.attempts; $summary.emulator_start_attempts | Should BeLessThan 3 }
            if ($case.output) { @($summary.emulator_stdout_paths).Count | Should Be 1; @($summary.emulator_stderr_paths).Count | Should Be 1; $summary.timestamp_beijing | Should Match '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$' }
            if ($null -ne $case.inputReady) { $summary.input_ready | Should Be $case.inputReady }
            if ($case.boot) { $summary.boot_completed | Should Be $case.boot; $summary.boot_animation | Should Be $case.bootanim; $summary.system_stable_samples | Should Be $case.stable }
            if ($case.systemDiagnostic) { $summary.system_diagnostics | Should Match $case.systemDiagnostic }
            if ($null -ne $case.foreground) { $summary.activity_foreground | Should Be $case.foreground; $summary.activity_surface | Should Be $case.surface }
            if ($null -ne $case.recoveries) { $summary.app_recovery_count | Should Be $case.recoveries }
            if ($null -ne $case.crashed) { $summary.app_crashed | Should Be $case.crashed }
        }
    }
}

Describe 'legacy fastboot configuration cleanup' {
    It 'keeps the first fastboot values and saves the original configuration' {
        $source = Get-Content -Raw -LiteralPath $scriptPath
        $functionText = [regex]::Match($source, '(?s)function Remove-LegacyFastbootDuplicates.*?(?=function Invoke-ControlledDryRun)').Value
        $script:recoveryActions = @()
        . ([scriptblock]::Create($functionText))
        $root = Join-Path $env:TEMP "mtl-fastboot-$([guid]::NewGuid().ToString('N'))"
        $avdPath = Join-Path $root 'target.avd'; $archive = Join-Path $root 'recovery'
        try {
            New-Item -ItemType Directory -Force -Path $avdPath, $archive | Out-Null
            Set-Content -LiteralPath (Join-Path $avdPath 'config.ini') -Value @('fastboot.forceColdBoot = no', 'fastboot.forceFastBoot = yes', 'fastboot.forceColdBoot = yes', 'fastboot.forceFastBoot = no', 'hw.ramSize = 2G')
            Remove-LegacyFastbootDuplicates $avdPath $archive
            $config = Get-Content -LiteralPath (Join-Path $avdPath 'config.ini')
            (@($config | Where-Object { $_ -match '^fastboot\.forceColdBoot' })).Count | Should Be 1
            ($config -join "`n") | Should Match 'fastboot.forceColdBoot = no'
            (Test-Path -LiteralPath (Join-Path $archive 'config.ini.before-fastboot-dedupe')) | Should Be $true
        } finally { if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force } }
    }
}

Describe 'Android SDK discovery' {
    It 'prefers a valid process candidate and falls back to a valid user candidate' {
        $source = Get-Content -Raw -LiteralPath $scriptPath
        $functionText = [regex]::Match($source, '(?s)function Resolve-AndroidSdk.*?(?=function Write-Stage)').Value
        . ([scriptblock]::Create($functionText))
        $root = Join-Path $env:TEMP "mtl-sdk-$([guid]::NewGuid().ToString('N'))"
        $processSdk = Join-Path $root 'process'; $userSdk = Join-Path $root 'user'
        try {
            foreach ($sdk in @($processSdk, $userSdk)) {
                New-Item -ItemType Directory -Force -Path (Join-Path $sdk 'platform-tools'), (Join-Path $sdk 'emulator') | Out-Null
                New-Item -ItemType File -Force -Path (Join-Path $sdk 'platform-tools\adb.exe'), (Join-Path $sdk 'emulator\emulator.exe') | Out-Null
            }
            (Resolve-AndroidSdk -ProcessCandidates @($processSdk) -UserCandidates @($userSdk) -LocalAppData '' -UserProfile '') | Should Be $processSdk
            (Resolve-AndroidSdk -ProcessCandidates @('', $null) -UserCandidates @($userSdk) -LocalAppData '' -UserProfile '') | Should Be $userSdk
        } finally { if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force } }
    }

    It 'returns null without throwing when every candidate is absent' {
        $source = Get-Content -Raw -LiteralPath $scriptPath
        $functionText = [regex]::Match($source, '(?s)function Resolve-AndroidSdk.*?(?=function Write-Stage)').Value
        . ([scriptblock]::Create($functionText))
        $missing = Join-Path $env:TEMP "mtl-sdk-missing-$([guid]::NewGuid().ToString('N'))"
        $result = Resolve-AndroidSdk -ProcessCandidates @($missing) -UserCandidates @() -LocalAppData '' -UserProfile ''
        [bool]$result | Should Be $false
        @($script:androidSdkCandidates).Count | Should Be 1
    }
}

Describe 'start-all Android handoff' {
    It 'preserves the Android exit code and surfaces its summary path' {
        $batch = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '..\..\start-all.bat')
        $batch | Should Match 'ANDROID_EXIT=%ERRORLEVEL%'
        $batch | Should Match 'ANDROID_SUMMARY'
        $batch | Should Match 'Android failure: stage='
        $batch | Should Match 'error_reason'
        (Get-Content -Raw -LiteralPath $scriptPath) | Should Match "throw 'runtime_state_unknown_lock'"
        $batch | Should Match 'START_EXIT=%ANDROID_EXIT%'
        $batch | Should Match '\$s\.input_ready -eq \$true'
        (Get-Content -Raw -LiteralPath $scriptPath) | Should Match "'-port', '5554'"
        (Get-Content -Raw -LiteralPath $scriptPath) | Should Match '\$windowPid = Get-TargetEmulatorPid'
        (Get-Content -Raw -LiteralPath $scriptPath) | Should Match 'App startup continues'
        (Get-Content -Raw -LiteralPath $scriptPath) | Should Match 'Wait-AndroidInputReady'
        (Get-Content -Raw -LiteralPath $scriptPath) | Should Match 'am force-stop com\.mytimelogger\.app'
        (Get-Content -Raw -LiteralPath $scriptPath) | Should Match 'shell reboot'
    }
}

Describe 'Android readiness contracts' {
    It 'waits for two stable system samples and bounded App readiness' {
        $source = Get-Content -Raw -LiteralPath $scriptPath
        $source | Should Match 'init\.svc\.bootanim'
        $source | Should Match 'systemStableSamples -ge 2'
        $source | Should Match 'Wait-AndroidAppReady'
        $source | Should Match 'appRecoveryCount -lt 1'
        $source | Should Match 'adb reboot disconnected transport'
        $source | Should Match 'window_service_pending'
        $source | Should Match "Can't find service: window"
    }
}

Describe 'Emulator output isolation contract' {
    It 'redirects diagnostics without opening another terminal' {
        $source = Get-Content -Raw -LiteralPath $scriptPath
        $source | Should Match 'RedirectStandardOutput'
        $source | Should Match 'RedirectStandardError'
        $source | Should Match 'NoNewWindow'
    }
}
