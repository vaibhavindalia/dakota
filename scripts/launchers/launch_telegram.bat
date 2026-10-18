@echo off
title DAKOTA - TELEGRAM SHELL BUILDER
color 0E
cls

echo ====================================================================
echo             DAKOTA TELEGRAM SHELL BUILDER / COLLECTOR
echo ====================================================================
echo.
echo [*] Component : Telethon MTProto Public Channel Investigator
echo [*] Target    : Real-time stock tip ingestion, parsing, scoring,
echo                 and live investigation record generation.
echo.
echo [*] Initializing Telegram environment...

for %%I in ("%~dp0..\..") do set "DAKOTA_ROOT=%%~fI"

cd /d "%DAKOTA_ROOT%"

set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"

if exist "%DAKOTA_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%DAKOTA_ROOT%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

if not exist "%DAKOTA_ROOT%\.env" (
    echo [!] WARNING: .env file not found in %DAKOTA_ROOT%.
    echo     Telegram API credentials [TELEGRAM_API_ID / TELEGRAM_API_HASH] are required.
    echo.
)

echo [*] Using Python: "%PYTHON_EXE%"
echo [*] Working Dir : "%DAKOTA_ROOT%"
echo [*] Script      : scripts\telegram\channel_reader.py
echo.
echo [*] Connecting to Telegram and monitoring channels...
echo.

"%PYTHON_EXE%" scripts\telegram\channel_reader.py

if %errorlevel% neq 0 (
    echo.
    echo ====================================================================
    echo [ERROR] Telegram Shell Builder exited with error code %errorlevel%.
    echo ====================================================================
    echo.
    echo Diagnostic Guidance:
    echo   1. Check your Internet connection (Wi-Fi / Ethernet).
    echo   2. Verify access to Telegram MTProto servers (port 443).
    echo   3. Ensure TELEGRAM_API_ID and TELEGRAM_API_HASH in .env are valid.
    echo   4. If on a restricted network / VPN, ensure outbound port 443 is permitted.
    echo.
)
echo.
echo Window will remain open for debugging. Press any key to exit.
pause >nul
