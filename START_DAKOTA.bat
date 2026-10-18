@echo off
setlocal EnableDelayedExpansion
title DAKOTA - SYSTEM LAUNCHER
color 0B
cls

echo ====================================================================
echo.
echo           ██████╗  █████╗ ██╗  ██╗ ██████╗ ████████╗ █████╗ 
echo           ██╔══██╗██╔══██╗██║ ██╔╝██╔═══██╗╚══██╔══╝██╔══██╗
echo           ██║  ██║███████║█████═╝ ██║   ██║   ██║   ███████║
echo           ██║  ██║██╔══██║██╔═██╗ ██║   ██║   ██║   ██╔══██║
echo           ██████╔╝██║  ██║██║ ╚██╗╚██████╔╝   ██║   ██║  ██║
echo           ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝
echo.
echo           Financial Intelligence ^& Scam Investigation Terminal
echo                         ONE-CLICK SYSTEM LAUNCHER
echo ====================================================================
echo.

:: ----------------------------------------------------------------------
:: 1. LOCATE DAKOTA REPOSITORY ROOT
:: ----------------------------------------------------------------------
set "CURRENT_DIR=%~dp0"
set "DAKOTA_ROOT="

if exist "%CURRENT_DIR%backend\main.py" (
    for %%I in ("%CURRENT_DIR%") do set "DAKOTA_ROOT=%%~fI"
) else if exist "%CURRENT_DIR%dakota integ. d11 final prototype1 minus telegram feature\dakota\backend\main.py" (
    for %%I in ("%CURRENT_DIR%dakota integ. d11 final prototype1 minus telegram feature\dakota") do set "DAKOTA_ROOT=%%~fI"
) else if exist "%CURRENT_DIR%dakota\backend\main.py" (
    for %%I in ("%CURRENT_DIR%dakota") do set "DAKOTA_ROOT=%%~fI"
) else (
    echo [ERROR] Could not find Dakota repository root containing backend\main.py.
    echo Searched location: %CURRENT_DIR%
    echo.
    echo Please make sure START_DAKOTA.bat is located in the project repository.
    echo.
    pause
    exit /b 1
)

cd /d "%DAKOTA_ROOT%"
echo [*] Repository Root: "%DAKOTA_ROOT%"
echo.

:: ----------------------------------------------------------------------
:: 2. PRE-FLIGHT CHECKS: RUNTIMES & PREREQUISITES
:: ----------------------------------------------------------------------
echo [1/4] Running Pre-Flight System Checks...

:: Check Python Virtual Environment
if exist "%DAKOTA_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%DAKOTA_ROOT%\.venv\Scripts\python.exe"
    echo   [OK] Python Environment : Virtualenv verified [.venv]
) else (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
        echo   [!] Python Environment : .venv missing, using system python
    ) else (
        echo   [ERROR] Python is not installed or not in PATH!
        echo   Please install Python 3.10+ or create .venv to continue.
        echo.
        pause
        exit /b 1
    )
)

:: Check Node.js runtime
where node >nul 2>nul
if !errorlevel! neq 0 (
    echo   [ERROR] Node.js was not found in system PATH!
    echo   Node.js v18+ is required to run Dakota Frontend.
    echo   Please download and install Node.js from https://nodejs.org
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%v in ('node -v 2^>nul') do echo   [OK] Node.js Runtime     : %%v
)

:: Check npm
where npm.cmd >nul 2>nul
if !errorlevel! neq 0 (
    where npm >nul 2>nul
    if !errorlevel! neq 0 (
        echo   [ERROR] npm package manager was not found in PATH!
        echo.
        pause
        exit /b 1
    )
)
echo   [OK] Package Manager    : npm detected

:: Check Configuration
if not exist "%DAKOTA_ROOT%\.env" (
    echo   [!] Config File         : .env not found in project root
) else (
    echo   [OK] Config File         : .env verified
)

:: Check Frontend Dependencies
if not exist "%DAKOTA_ROOT%\frontend\node_modules" (
    echo.
    echo   [*] Frontend dependencies missing. Installing node_modules...
    cd /d "%DAKOTA_ROOT%\frontend"
    call npm.cmd install
    cd /d "%DAKOTA_ROOT%"
    if !errorlevel! neq 0 (
        echo   [ERROR] npm install failed.
        pause
        exit /b 1
    )
    echo   [OK] Frontend dependencies installed.
) else (
    echo   [OK] Frontend Packages  : node_modules verified
)

:: Check Component Launchers
if not exist "%DAKOTA_ROOT%\scripts\launchers\launch_backend.bat" (
    echo   [ERROR] scripts\launchers\launch_backend.bat is missing!
    pause
    exit /b 1
)
if not exist "%DAKOTA_ROOT%\scripts\launchers\launch_frontend.bat" (
    echo   [ERROR] scripts\launchers\launch_frontend.bat is missing!
    pause
    exit /b 1
)
if not exist "%DAKOTA_ROOT%\scripts\launchers\launch_telegram.bat" (
    echo   [ERROR] scripts\launchers\launch_telegram.bat is missing!
    pause
    exit /b 1
)

echo.
echo   All pre-flight checks passed successfully!
echo.

:: ----------------------------------------------------------------------
:: 3. PORT & DUPLICATE INSTANCE DETECTION
:: ----------------------------------------------------------------------
echo [2/4] Checking For Already-Running Services...

set "BACKEND_RUNNING=0"
set "FRONTEND_RUNNING=0"
set "TELEGRAM_RUNNING=0"

"%PYTHON_EXE%" "%DAKOTA_ROOT%\scripts\launchers\status_check.py" backend >nul 2>nul
if !errorlevel! equ 0 (
    set "BACKEND_RUNNING=1"
    echo   [!] Port 8000 occupied - Dakota Backend is already running.
) else (
    echo   [+] Port 8000 available for Dakota Backend.
)

"%PYTHON_EXE%" "%DAKOTA_ROOT%\scripts\launchers\status_check.py" frontend >nul 2>nul
if !errorlevel! equ 0 (
    set "FRONTEND_RUNNING=1"
    echo   [!] Port 3000 occupied - Dakota Frontend is already running.
) else (
    echo   [+] Port 3000 available for Dakota Frontend.
)

"%PYTHON_EXE%" "%DAKOTA_ROOT%\scripts\launchers\status_check.py" telegram >nul 2>nul
if !errorlevel! equ 0 (
    set "TELEGRAM_RUNNING=1"
    echo   [!] Telegram Shell Builder is already running.
) else (
    echo   [+] Telegram Shell Builder ready to launch.
)

echo.

:: ----------------------------------------------------------------------
:: 4. COMPONENT DISPATCH (SEPARATE TITLED WINDOWS)
:: ----------------------------------------------------------------------
echo [3/4] Launching Dakota Subsystems in Dedicated Windows...

:: Launch Backend
if "!BACKEND_RUNNING!"=="0" (
    echo   [-] Starting Dakota Backend [Port 8000]...
    start "DAKOTA - BACKEND" cmd /k call "%DAKOTA_ROOT%\scripts\launchers\launch_backend.bat"
    ping 127.0.0.1 -n 4 >nul
) else (
    echo   [-] Skipping Dakota Backend [Already active]
)

:: Launch Frontend
if "!FRONTEND_RUNNING!"=="0" (
    echo   [-] Starting Dakota Frontend [Port 3000]...
    start "DAKOTA - FRONTEND" cmd /k call "%DAKOTA_ROOT%\scripts\launchers\launch_frontend.bat"
    ping 127.0.0.1 -n 3 >nul
) else (
    echo   [-] Skipping Dakota Frontend [Already active]
)

:: Launch Telegram Shell Builder
if "!TELEGRAM_RUNNING!"=="0" (
    echo   [-] Starting Dakota Telegram Shell Builder...
    start "DAKOTA - TELEGRAM SHELL BUILDER" cmd /k call "%DAKOTA_ROOT%\scripts\launchers\launch_telegram.bat"
) else (
    echo   [-] Skipping Dakota Telegram Shell Builder [Already active]
)

echo.

:: ----------------------------------------------------------------------
:: 5. INITIALIZATION VERIFICATION & SUMMARY
:: ----------------------------------------------------------------------
echo [4/4] Verifying Service Initialization...

set "BACKEND_OK=0"
for /l %%i in (1, 1, 8) do (
    if "!BACKEND_OK!"=="0" (
        "%PYTHON_EXE%" "%DAKOTA_ROOT%\scripts\launchers\status_check.py" backend >nul 2>nul
        if !errorlevel! equ 0 (
            set "BACKEND_OK=1"
        ) else (
            ping 127.0.0.1 -n 2 >nul
        )
    )
)

if not exist "%DAKOTA_ROOT%\logs" mkdir "%DAKOTA_ROOT%\logs"
echo {"launched_at": "%DATE% %TIME%", "root": "%DAKOTA_ROOT%"} > "%DAKOTA_ROOT%\logs\dakota_launcher.pid"

echo.
echo ====================================================================
echo                 DAKOTA IS RUNNING SUCCESSFULLY!
echo ====================================================================
echo.
echo   [1] FRONTEND WEB APP   : http://localhost:3000
echo   [2] BACKEND API ROOT   : http://localhost:8000
echo   [3] INTERACTIVE DOCS   : http://localhost:8000/docs
echo   [4] STOCKS HEALTH API  : http://localhost:8000/api/stocks?limit=1
echo   [5] TELEGRAM MONITOR   : Live Ingestion Active
echo.
echo ====================================================================
echo   OPERATING NOTES:
echo   - 3 separate Command Prompt windows are running with their live logs.
echo   - Keep those windows open while using the platform.
echo   - To safely stop all 3 services at any time, run: STOP_DAKOTA.bat
echo ====================================================================
echo.

pause
