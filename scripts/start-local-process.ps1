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
        return ($commandLine -like "*$root*") -and ($commandLine -match 'vite')
    }
    return $false
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
        'Vite' { @{ Directory = (Join-Path $root 'ui'); Command = 'npm run dev'; Port = 5173; Url = 'http://127.0.0.1:5173/'; Marker = 'vite' } }
        'Electron' { @{ Directory = (Join-Path $root 'desktop'); Command = 'set MTL_DEV_SERVER_URL=http://127.0.0.1:5173&& set MTL_LOAD_DEV_SERVER=1&& npm start' } }
    }
    if ($Name -eq 'Server') {
        $serverEntry = Join-Path $root 'server\server.py'
        & python -m py_compile $serverEntry
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    if ($Name -eq 'Electron') {
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
            Start-Sleep -Milliseconds 250
            $viteChild = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.Id)" -ErrorAction SilentlyContinue | Where-Object {
                ([string]$_.CommandLine -like "*$root*") -and ([string]$_.CommandLine -match 'vite')
            } | Select-Object -First 1
            if ($viteChild) { $trackedProcessId = [int]$viteChild.ProcessId }
        }
        $runId = if ($env:MTL_STARTUP_RUN_ID) { $env:MTL_STARTUP_RUN_ID } else { [guid]::NewGuid().ToString('N') }
        [pscustomobject]@{
            run_id = $runId; pid = $trackedProcessId; endpoint = $Name
            started_at_beijing = [DateTime]::UtcNow.AddHours(8).ToString('o')
            stdout_path = $output; stderr_path = $errorLog
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDirectory "$safeName.state.json") -Encoding utf8
    }
    if ($Name -eq 'Electron') {
        Write-Host "[start] Fresh Electron launch requested: PID $($process.Id). Logs: $output"
    } else {
        Write-Host "[start] $Name started: PID $($process.Id), logs: $output"
    }
} catch {
    [Console]::Error.WriteLine("[start] $Name failed: $($_.Exception.Message)")
    exit 1
}
