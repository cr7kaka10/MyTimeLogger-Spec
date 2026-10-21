param([ValidateSet('Server', 'Vite', 'Electron')] [string]$Name)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDirectory = Join-Path $root 'tests\runtime\startup-logs'
$finalBackupVersion = 2
$checklistResetVersion = 1
$expectedBuild = ''
try { $expectedBuild = (& git -C $root rev-parse --short=12 HEAD 2>$null).Trim() } catch {}

function Test-ProjectProcess([int]$ProcessId, [string]$ProcessName) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $processInfo) { return $false }
    $commandLine = [string]$processInfo.CommandLine
    if ($ProcessName -eq 'Server') {
        return ($commandLine -match 'uvicorn\s+server\.server:app')
    }
    if ($ProcessName -eq 'Vite') {
        return ($commandLine -like "*$root*") -and ($commandLine -match '[/\\]vite[/\\](bin|dist)[/\\]')
    }
    return $false
}

function Get-VerifiedViteState([switch]$RequireCurrentRun, [switch]$RequireAddress) {
    $path = Join-Path $logDirectory 'Vite.state.json'
    if (-not (Test-Path -LiteralPath $path)) { return @{ Valid = $false; Reason = 'missing_state' } }
    try { $state = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json }
    catch { return @{ Valid = $false; Reason = 'invalid_state' } }
    if ($state.endpoint -ne 'Vite' -or -not $state.pid) { return @{ Valid = $false; Reason = 'invalid_state' } }
    if ($RequireCurrentRun -and $env:MTL_STARTUP_RUN_ID -and $state.run_id -ne $env:MTL_STARTUP_RUN_ID) {
        return @{ Valid = $false; Reason = 'stale_state' }
    }
    if (-not (Test-ProjectProcess -ProcessId ([int]$state.pid) -ProcessName Vite)) {
        return @{ Valid = $false; Reason = 'process_not_project_owned' }
    }
    $statePort = 0
    if ($RequireAddress -and (-not [int]::TryParse([string]$state.port, [ref]$statePort) -or
            $statePort -lt 1 -or $statePort -gt 65535 -or
            $state.url -ne "http://127.0.0.1:$statePort/")) {
        return @{ Valid = $false; Reason = 'invalid_address' }
    }
    return @{ Valid = $true; State = $state }
}

function Find-ProjectViteChild([int]$LauncherPid) {
    $parents = @($LauncherPid)
    for ($depth = 0; $depth -lt 5 -and $parents.Count; $depth++) {
        $children = @(foreach ($parentId in $parents) {
            Get-CimInstance Win32_Process -Filter "ParentProcessId = $parentId" -ErrorAction SilentlyContinue
        })
        foreach ($child in $children) {
            if (Test-ProjectProcess -ProcessId ([int]$child.ProcessId) -ProcessName Vite) {
                return [int]$child.ProcessId
            }
        }
        $parents = @($children | ForEach-Object { [int]$_.ProcessId })
    }
    return $null
}

function Get-ProjectElectronPrimaries {
    $electronPath = [System.IO.Path]::GetFullPath((Join-Path $root 'desktop\node_modules\electron\dist\electron.exe'))
    if (-not (Test-Path -LiteralPath $electronPath)) { return @() }
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and
        [System.IO.Path]::GetFullPath($_.ExecutablePath).Equals($electronPath, [System.StringComparison]::OrdinalIgnoreCase) -and
        ([string]$_.CommandLine -notmatch '--type=')
    })
}

try {
    $serverBuildEnvironment = if ($expectedBuild) { "set MTL_BUILD_REVISION=$expectedBuild&& " } else { '' }
    $definition = switch ($Name) {
        'Server' { @{ Directory = $root; Command = "${serverBuildEnvironment}python -m uvicorn server.server:app --app-dir `"$root`" --host 0.0.0.0 --port 8000"; Port = 8000; Url = 'http://127.0.0.1:8000/ping'; Marker = 'server' } }
        'Vite' { @{ Directory = (Join-Path $root 'ui'); Command = 'npm run dev'; Marker = 'vite' } }
        'Electron' { @{ Directory = (Join-Path $root 'desktop'); Command = 'npm start' } }
    }
    if ($Name -eq 'Server') {
        $serverEntry = Join-Path $root 'server\server.py'
        & python -m py_compile $serverEntry
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    if ($Name -eq 'Vite') {
        $previous = Get-VerifiedViteState
        if ($previous.Valid) {
            Stop-Process -Id ([int]$previous.State.pid) -Force -ErrorAction Stop
            $stopDeadline = [DateTime]::UtcNow.AddSeconds(10)
            while ((Get-Process -Id ([int]$previous.State.pid) -ErrorAction SilentlyContinue) -and
                    [DateTime]::UtcNow -lt $stopDeadline) { Start-Sleep -Milliseconds 100 }
            if (Get-Process -Id ([int]$previous.State.pid) -ErrorAction SilentlyContinue) {
                throw "Verified Vite PID $($previous.State.pid) did not stop"
            }
            Write-Host "[start] Stopped verified MyTimeLogger Vite PID $($previous.State.pid)."
        }
    }
    if ($Name -eq 'Vite') {
        $portOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'select-local-ui-port.ps1') 2>&1
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("[start] $($portOutput -join ' ')")
            exit 2
        }
        $definition.Port = [int]($portOutput | Select-Object -Last 1)
        $definition.Url = "http://127.0.0.1:$($definition.Port)/"
        $definition.Command = "npm run dev -- --port $($definition.Port) --strictPort"
    }
    if ($Name -eq 'Electron') {
        $viteState = Get-VerifiedViteState -RequireCurrentRun -RequireAddress
        if (-not $viteState.Valid) { throw "Vite state rejected: $($viteState.Reason)" }
        $definition.Command = "set MTL_DEV_SERVER_URL=$($viteState.State.url)&& set MTL_LOAD_DEV_SERVER=1&& npm start"
        $electronPrimaries = @(Get-ProjectElectronPrimaries)
        foreach ($primary in $electronPrimaries) {
            Stop-Process -Id ([int]$primary.ProcessId) -Force -ErrorAction Stop
        }
        if ($electronPrimaries.Count) {
            $pids = $electronPrimaries.ProcessId
            $deadline = [DateTime]::UtcNow.AddSeconds(10)
            while ([DateTime]::UtcNow -lt $deadline) {
                $running = @(Get-Process -Id $pids -ErrorAction SilentlyContinue)
                if (-not $running.Count) { break }
                Start-Sleep -Milliseconds 100
            }
            if (@(Get-Process -Id $pids -ErrorAction SilentlyContinue).Count) {
                [Console]::Error.WriteLine('[start] Verified MyTimeLogger Electron did not stop.')
                exit 2
            }
            Write-Host "[start] Replaced verified MyTimeLogger Electron primary PID $($pids -join ',')."
        }
    }
    if ($definition.Port) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $definition.Port -ErrorAction SilentlyContinue)
        if ($listeners.Count) {
            $ownerPids = @($listeners.OwningProcess | Sort-Object -Unique)
            $unknownPids = @($ownerPids | Where-Object { -not (Test-ProjectProcess -ProcessId $_ -ProcessName $Name) })
            if ($unknownPids.Count) {
                [Console]::Error.WriteLine("[start] Port $($definition.Port) includes unknown PID $($unknownPids -join ','); refusing to stop it.")
                exit 2
            }
            foreach ($ownerPid in $ownerPids) {
                Stop-Process -Id $ownerPid -Force -ErrorAction Stop
            }
            $deadline = [DateTime]::UtcNow.AddSeconds(10)
            while ((Get-NetTCPConnection -State Listen -LocalPort $definition.Port -ErrorAction SilentlyContinue) -and
                    [DateTime]::UtcNow -lt $deadline) {
                Start-Sleep -Milliseconds 100
            }
            if (Get-NetTCPConnection -State Listen -LocalPort $definition.Port -ErrorAction SilentlyContinue) {
                [Console]::Error.WriteLine("[start] $Name PID stopped but port $($definition.Port) did not become free.")
                exit 2
            }
            Write-Host "[start] Restarting verified $Name to load the current workspace."
        }
    }
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    $safeName = $Name -replace '[^A-Za-z0-9_-]', '-'
    $output = Join-Path $logDirectory "$safeName.out.log"
    $errorLog = Join-Path $logDirectory "$safeName.err.log"
    $process = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/c', $definition.Command) `
        -WorkingDirectory $definition.Directory -WindowStyle Hidden `
        -RedirectStandardOutput $output -RedirectStandardError $errorLog -PassThru
    if ($Name -in @('Server', 'Vite')) {
        $trackedProcessId = $process.Id
        if ($Name -eq 'Vite') {
            $deadline = [DateTime]::UtcNow.AddSeconds(8)
            do {
                $viteChildPid = Find-ProjectViteChild -LauncherPid ([int]$process.Id)
                if ($viteChildPid) { $trackedProcessId = $viteChildPid; break }
                Start-Sleep -Milliseconds 100
            } while ([DateTime]::UtcNow -lt $deadline)
            if (-not $viteChildPid) { throw 'Vite process did not become identifiable' }
        }
        $runId = if ($env:MTL_STARTUP_RUN_ID) { $env:MTL_STARTUP_RUN_ID } else { [guid]::NewGuid().ToString('N') }
        [pscustomobject]@{
            run_id = $runId; pid = $trackedProcessId; endpoint = $Name
            port = $definition.Port; url = $definition.Url
            started_at_beijing = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('o')
            stdout_path = $output; stderr_path = $errorLog
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDirectory "$safeName.state.json") -Encoding utf8
    }
    if ($Name -eq 'Electron') {
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            $ready = @(Get-ProjectElectronPrimaries | Where-Object {
                $candidate = Get-Process -Id ([int]$_.ProcessId) -ErrorAction SilentlyContinue
                $candidate -and $candidate.MainWindowHandle -ne 0
            }) | Select-Object -First 1
            if ($ready) { break }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not $ready) {
            $tail = if (Test-Path -LiteralPath $errorLog) {
                (Get-Content -LiteralPath $errorLog -Tail 10 -ErrorAction SilentlyContinue) -join ' | '
            } else { '(stderr log unavailable)' }
            [Console]::Error.WriteLine("[start] Electron window_not_ready after 30s. Logs: $errorLog. Tail: $tail")
            exit 2
        }
        Write-Host "[start] Electron window ready: PID $($ready.ProcessId). Logs: $output"
    } else {
        Write-Host "[start] $Name started: PID $($process.Id), logs: $output"
    }
} catch {
    [Console]::Error.WriteLine("[start] $Name failed: $($_.Exception.Message)")
    exit 1
}
