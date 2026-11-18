<#
.SYNOPSIS
    Smart Hotel Monitoring System (SHMS) - Edge Server PowerShell Launcher

.DESCRIPTION
    Single-command launcher for SHMS Edge Node. Automatically detects Python,
    manages the .venv environment, verifies configurations, and launches the server.

.PARAMETER HostAddress
    Host IP address to bind (default: 0.0.0.0).

.PARAMETER Port
    HTTP port to bind (default: 8000).

.PARAMETER NoBrowser
    Prevents automatically opening the dashboard in the default browser.

.PARAMETER Reload
    Enables uvicorn auto-reload on code change.

.PARAMETER Install
    Forces re-install/update of dependencies from requirements.txt.

.EXAMPLE
    .\run.ps1
    .\run.ps1 -Port 8080 -NoBrowser
#>

[CmdletBinding()]
param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$NoBrowser,
    [switch]$Reload,
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "   SMART HOTEL MONITORING SYSTEM (SHMS) - EDGE NODE LAUNCHER" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# 1. Resolve Python executable
$PythonExe = $null

# Check local .venv
if (Test-Path "$ScriptDir\.venv\Scripts\python.exe") {
    $PythonExe = "$ScriptDir\.venv\Scripts\python.exe"
}
# Check command 'python'
elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $PythonExe = (Get-Command "python").Source
}
# Check uv python path
elseif (Test-Path "$env:APPDATA\uv\python\cpython-3.11.13-windows-x86_64-none\python.exe") {
    $PythonExe = "$env:APPDATA\uv\python\cpython-3.11.13-windows-x86_64-none\python.exe"
}
# Check LocalAppData Programs
elseif (Test-Path "$env:LOCALAPPDATA\Programs\Python") {
    $found = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter "python.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $PythonExe = $found.FullName }
}

if (-not $PythonExe) {
    Write-Host "[ERROR] Could not locate a working Python executable." -ForegroundColor Red
    Write-Host "Please ensure Python 3.10+ is installed or on PATH." -ForegroundColor Yellow
    exit 1
}

# 2. Check if .venv exists; if not, create it
if (-not (Test-Path "$ScriptDir\.venv\Scripts\python.exe")) {
    Write-Host "[i] Initializing local virtual environment in .venv..." -ForegroundColor Yellow
    $uvExe = "$env:LOCALAPPDATA\Programs\Python\Python310\Scripts\uv.exe"
    if (Test-Path $uvExe) {
        & $uvExe venv "$ScriptDir\.venv" --python $PythonExe
    } else {
        & $PythonExe -m venv "$ScriptDir\.venv"
    }
    if (Test-Path "$ScriptDir\.venv\Scripts\python.exe") {
        $PythonExe = "$ScriptDir\.venv\Scripts\python.exe"
        Write-Host "[i] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
        & $PythonExe -m pip install -r requirements.txt
    }
}

# 3. Optional install flag
if ($Install) {
    Write-Host "[i] Updating dependencies from requirements.txt..." -ForegroundColor Yellow
    & $PythonExe -m pip install -r requirements.txt
}

# 4. Check & Build Frontend Dashboard if missing
$DistIndex = "$ScriptDir\frontend\dist\index.html"
if (-not (Test-Path $DistIndex)) {
    Write-Host "[!] Prebuilt dashboard not found at frontend\dist\index.html." -ForegroundColor Yellow
    if (Get-Command "npm" -ErrorAction SilentlyContinue) {
        Write-Host "[i] Node.js/npm detected. Auto-building React dashboard..." -ForegroundColor Cyan
        Push-Location "$ScriptDir\frontend"
        try {
            if (-not (Test-Path "node_modules")) {
                Write-Host "[i] Installing frontend dependencies (npm install)..." -ForegroundColor Yellow
                & npm install
            }
            Write-Host "[i] Compiling production bundle (npm run build)..." -ForegroundColor Yellow
            & npm run build
            Write-Host "[✓] Frontend built successfully!" -ForegroundColor Green
        } catch {
            Write-Host "[!] Warning: npm build failed ($($_.Exception.Message)). Fallback UI will be served." -ForegroundColor Red
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "[i] Node.js/npm not found. Backend will serve diagnostic status page until built." -ForegroundColor Yellow
    }
}

# 5. Build argument list
$RunArgs = @("run.py", "--host", $HostAddress, "--port", $Port)
if ($NoBrowser) { $RunArgs += "--no-browser" }
if ($Reload) { $RunArgs += "--reload" }

# 6. Execute
Write-Host "[✓] Launching Edge Server via $PythonExe..." -ForegroundColor Green
& $PythonExe $RunArgs
