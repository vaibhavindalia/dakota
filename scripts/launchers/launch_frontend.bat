@echo off
title DAKOTA - FRONTEND
color 0A
cls

echo ====================================================================
echo                 DAKOTA FRONTEND - WEB APPLICATION
echo ====================================================================
echo.
echo [*] Component : Next.js Dev Server (Turbopack)
echo [*] Port      : 3000 (http://localhost:3000)
echo.
echo [*] Initializing frontend environment...

for %%I in ("%~dp0..\..\frontend") do set "FRONTEND_DIR=%%~fI"

cd /d "%FRONTEND_DIR%"

if not exist "%FRONTEND_DIR%\node_modules" (
    echo.
    echo [!] WARNING: node_modules directory not detected in %FRONTEND_DIR%!
    echo [*] Running 'npm install' to install dependencies...
    call npm.cmd install
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install npm dependencies.
        pause
        exit /b 1
    )
)

echo [*] Working Dir : "%FRONTEND_DIR%"
echo [*] Starting Next.js development server...
echo [*] Dakota Web UI will be available at: http://localhost:3000
echo.

call npm.cmd run dev

if %errorlevel% neq 0 (
    echo.
    echo ====================================================================
    echo [ERROR] Dakota Frontend exited with error code %errorlevel%.
    echo Review the error log above for details.
    echo ====================================================================
)
echo.
echo Window will remain open for debugging. Press any key to exit.
pause >nul
