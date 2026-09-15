param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$uiDir = Join-Path $root "ui"
$androidDir = Join-Path $uiDir "android"
$gradleWrapper = Join-Path $androidDir "gradlew.bat"
$outputDir = Join-Path $root "deploy\artifacts"
$outputPath = Join-Path $outputDir "MyTimeLogger-debug.apk"
$apkSource = Join-Path $androidDir "app\build\outputs\apk\debug\app-debug.apk"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is missing: $Name"
    }
}

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (exit $LASTEXITCODE)."
    }
}

try {
    Require-Command "node"
    Require-Command "npm"
    Require-Command "npx"

    $sdkCandidates = @($env:ANDROID_SDK_ROOT, $env:ANDROID_HOME)
    if ($env:LOCALAPPDATA) {
        $sdkCandidates += Join-Path $env:LOCALAPPDATA "Android\Sdk"
    }
    $androidSdk = $sdkCandidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } |
        Select-Object -First 1
    if (-not $androidSdk) {
        throw "Android SDK is missing. Set ANDROID_SDK_ROOT or ANDROID_HOME."
    }

    $jdkCandidates = @($env:JAVA_HOME)
    if ($env:ProgramFiles) {
        $jdkCandidates += Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
    }
    $jdkHome = $null
    foreach ($candidate in $jdkCandidates) {
        if (-not $candidate -or -not (Test-Path (Join-Path $candidate "bin\java.exe"))) {
            continue
        }
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $version = (& (Join-Path $candidate "bin\java.exe") -version 2>&1 | Out-String)
        $ErrorActionPreference = $previousErrorAction
        if ($version -match 'version "21') {
            $jdkHome = $candidate
            break
        }
    }
    if (-not $jdkHome) {
        throw "JDK 21 is missing. Set JAVA_HOME or install Android Studio JBR 21."
    }
    if (-not (Test-Path -LiteralPath $gradleWrapper -PathType Leaf)) {
        throw "Gradle wrapper is missing: $gradleWrapper"
    }

    $env:ANDROID_HOME = $androidSdk
    $env:ANDROID_SDK_ROOT = $androidSdk
    $env:JAVA_HOME = $jdkHome
    $env:PATH = "$(Join-Path $jdkHome 'bin');$env:PATH"

    if (Test-Path -LiteralPath $outputPath) {
        Remove-Item -LiteralPath $outputPath -Force
    }
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    Push-Location $uiDir
    try {
        Write-Host "[Android] Building web staging..."
        Invoke-Checked "npm run build:android-web" { npm run build:android-web }
        Write-Host "[Android] Synchronizing Capacitor..."
        Invoke-Checked "npx cap sync android" { npx cap sync android }
    } finally {
        Pop-Location
    }

    Push-Location $androidDir
    try {
        Write-Host "[Android] Building Debug APK..."
        Invoke-Checked "Gradle assembleDebug" { & $gradleWrapper assembleDebug }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path -LiteralPath $apkSource -PathType Leaf)) {
        throw "Gradle completed but APK was not found: $apkSource"
    }
    Copy-Item -LiteralPath $apkSource -Destination $outputPath -Force
    $sizeMb = [math]::Round((Get-Item -LiteralPath $outputPath).Length / 1MB, 1)
    Write-Host "[OK] Android Debug APK: $outputPath ($sizeMb MB)"
    exit 0
} catch {
    Write-Host "[FAIL] Android APK build failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
