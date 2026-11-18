@echo off
setlocal enabledelayedexpansion

title Smart Hotel Monitoring System - Edge Vision Server
cd /d "%~dp0"

echo ========================================================================
echo   SMART HOTEL MONITORING SYSTEM (SHMS) - EDGE NODE LAUNCHER
echo ========================================================================
echo.

:: 1. Detect Python Executable
set "PYTHON_EXE="

:: Check local .venv first
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)

:: Check system python
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%i"
    goto :PYTHON_FOUND
)

:: Check py launcher
for /f "tokens=*" %%i in ('where py 2^>nul') do (
    set "PYTHON_EXE=py -3"
    goto :PYTHON_FOUND
)

:: Check uv installed python path
if exist "%APPDATA%\uv\python\cpython-3.11.13-windows-x86_64-none\python.exe" (
    set "PYTHON_EXE=%APPDATA%\uv\python\cpython-3.11.13-windows-x86_64-none\python.exe"
    goto :PYTHON_FOUND
)

:: Check standard LocalAppData Python
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :PYTHON_FOUND
    )
)

:PYTHON_FOUND
if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found on your system!
    echo Please install Python 3.10+ or run 'uv python install 3.11'
    echo.
    pause
    exit /b 1
)

:: 2. Auto-create .venv if missing and uv or python available
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [i] Setting up local virtual environment (.venv)...
    if exist "%LOCALAPPDATA%\Programs\Python\Python310\Scripts\uv.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python310\Scripts\uv.exe" venv .venv --python "%PYTHON_EXE%"
    ) else (
        "%PYTHON_EXE%" -m venv .venv
    )
    if exist "%~dp0.venv\Scripts\python.exe" (
        set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
        echo [i] Installing dependencies from requirements.txt...
        "%PYTHON_EXE%" -m pip install -r requirements.txt
    )
)

:: 3. Check and build frontend if missing
if not exist "%~dp0frontend\dist\index.html" (
    echo [!] Prebuilt dashboard not found in frontend\dist.
    where npm >nul 2>&1
    if !errorlevel! EQU 0 (
        echo [i] Node.js/npm detected. Auto-building React dashboard...
        pushd "%~dp0frontend"
        if not exist "node_modules" (
            echo [i] Installing npm packages...
            call npm install
        )
        echo [i] Compiling production bundle (npm run build)...
        call npm run build
        popd
        echo [✓] Frontend built successfully.
    ) else (
        echo [i] Note: Node.js/npm not found. Backend will serve setup page until built.
    )
)

:: 4. Launch via run.py
"%PYTHON_EXE%" run.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Server process exited with code %ERRORLEVEL%.
    pause
)
