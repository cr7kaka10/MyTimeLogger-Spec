param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("development", "testing", "production")]
    [string]$Environment,

    [string]$ConfigPath,
    [string]$ConfigRoot,
    [switch]$RequireComplete,
    [switch]$Quiet,
    [switch]$EmitCmd
)

$ErrorActionPreference = "Stop"
$ConfigRoot = if ($ConfigRoot) { $ConfigRoot } else { $PSScriptRoot }

if (-not $ConfigPath) {
    $canonicalPath = Join-Path $ConfigRoot "config.local.env"
    $legacyPath = Join-Path $ConfigRoot "config.$Environment.local.env"
    if (Test-Path -LiteralPath $canonicalPath) {
        $ConfigPath = $canonicalPath
    } elseif (Test-Path -LiteralPath $legacyPath) {
        $ConfigPath = $legacyPath
        if (-not $Quiet) { Write-Warning "Deprecated private config name; migrate to config.local.env" }
    } else {
        throw "Private config file not found: $canonicalPath"
    }
}

function ConvertTo-EnvName([string]$key) {
    return ($key.Trim() -replace '[^A-Za-z0-9_]', '_').ToUpperInvariant()
}

function Set-EnvValue([string]$key, [string]$value) {
    $name = ConvertTo-EnvName $key
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

function Load-EnvFile([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Private config file not found: $path"
    }
    $loaded = [ordered]@{}
    foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1)
        if ($key -in @("MTL_ENVIRONMENT", "MTL_USERNAME", "MTL_SERVER_URL")) { continue }
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-EnvValue $key $value
        $loaded[(ConvertTo-EnvName $key)] = $value
    }
    return $loaded
}

$values = Load-EnvFile $ConfigPath
[Environment]::SetEnvironmentVariable("MYTIMELOGGER_ENVIRONMENT", $Environment, "Process")

$required = @("MTL_SERVER_HOST", "MTL_SERVER_USER", "MTL_REMOTE_DIR", "MTL_APP_PORT")
if ($RequireComplete) {
    $missing = @()
    foreach ($name in $required) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrWhiteSpace($value)) { $missing += $name }
    }
    if ($missing.Count -gt 0) {
        throw "Missing required config fields: $($missing -join ', ')"
    }
}

if ($EmitCmd) {
    foreach ($name in @("MTL_SERVER_HOST", "MTL_SERVER_PORT", "MTL_SERVER_USER", "MTL_REMOTE_DIR", "MTL_APP_PORT", "MYTIMELOGGER_ENVIRONMENT")) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($null -ne $value) { Write-Output ('set "{0}={1}"' -f $name, $value.Replace('%', '%%')) }
    }
    Write-Output 'set "MTL_CONFIG_LOAD_OK=1"'
} elseif (-not $Quiet) {
    Write-Host "[config] Loaded $Environment private config: $ConfigPath"
    foreach ($name in @("MTL_SERVER_HOST", "MTL_SERVER_PORT", "MTL_SERVER_USER", "MTL_REMOTE_DIR", "MTL_APP_PORT")) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($null -ne $value) {
            $status = if ([string]::IsNullOrWhiteSpace($value)) { "missing" } else { "configured" }
            Write-Host ("[config] {0} {1}" -f $name, $status)
        }
    }
}

$script:LoadedPrivateEnv = $values
