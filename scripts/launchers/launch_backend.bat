@echo off
title DAKOTA - BACKEND
color 0B
cls

echo ====================================================================
echo                 DAKOTA BACKEND - API SERVER
echo ====================================================================
echo.
echo [*] Component : FastAPI / Uvicorn Server
echo [*] Port      : 8000 (http://localhost:8000)
echo [*] API Docs  : http://localhost:8000/docs
echo [*] Stocks API: http://localhost:8000/api/stocks?limit=1
echo.
echo [*] Initializing backend environment...

for %%I in ("%~dp0..\..") do set "DAKOTA_ROOT=%%~fI"

cd /d "%DAKOTA_ROOT%"

set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"

if exist "%DAKOTA_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%DAKOTA_ROOT%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Using Python: "%PYTHON_EXE%"
echo [*] Working Dir : "%DAKOTA_ROOT%"
echo.
echo [*] Starting Uvicorn server on http://0.0.0.0:8000...
echo.

"%PYTHON_EXE%" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

if %errorlevel% neq 0 (
    echo.
    echo ====================================================================
    echo [ERROR] Dakota Backend exited with error code %errorlevel%.
    echo Review the traceback above for details.
    echo ====================================================================
)
echo.
echo Window will remain open for debugging. Press any key to exit.
pause >nul
