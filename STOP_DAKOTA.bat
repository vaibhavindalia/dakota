@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title DAKOTA - SAFE SYSTEM SHUTDOWN
color 0C
cls

echo ====================================================================
echo.
echo           ==============================================
echo                         D A K O T A
echo                 SAFE TERMINATION & SHUTDOWN CONTROLLER
echo           ==============================================
echo.
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
    pause
    exit /b 1
)

cd /d "%DAKOTA_ROOT%"
echo [*] Repository Root: "%DAKOTA_ROOT%"
echo.

:: ----------------------------------------------------------------------
:: 2. DETECT PYTHON ENVIRONMENT
:: ----------------------------------------------------------------------
if exist "%DAKOTA_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%DAKOTA_ROOT%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: ----------------------------------------------------------------------
:: 3. EXECUTE TARGETED SHUTDOWN CONTROLLER
:: ----------------------------------------------------------------------
if exist "%DAKOTA_ROOT%\scripts\launchers\stop_services.py" (
    "%PYTHON_EXE%" "%DAKOTA_ROOT%\scripts\launchers\stop_services.py"
) else (
    echo [*] Running fallback termination logic...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
        echo [*] Stopping PID on port 8000: %%a
        taskkill /F /PID %%a >nul 2>nul
    )
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
        echo [*] Stopping PID on port 3000: %%a
        taskkill /F /T /PID %%a >nul 2>nul
    )
)

echo.
echo Press any key to close this window.
pause >nul
