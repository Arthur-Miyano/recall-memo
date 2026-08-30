@echo off
setlocal
cd /d %~dp0

REM ---- First-run setup: frontend deps + build ----
if not exist frontend\node_modules (
    echo [Recall] First run: installing frontend dependencies...
    pushd frontend
    call npm install || (echo npm install failed & popd & pause & exit /b 1)
    popd
)
if not exist frontend\dist\index.html (
    echo [Recall] Building frontend...
    pushd frontend
    call npm run build || (echo frontend build failed & popd & pause & exit /b 1)
    popd
)

REM ---- First-run setup: backend venv + deps ----
if not exist backend\.venv\Scripts\python.exe (
    echo [Recall] First run: creating Python venv and installing backend dependencies...
    pushd backend
    python -m venv .venv || (echo failed to create venv - need Python 3.11+ on PATH & popd & pause & exit /b 1)
    .venv\Scripts\python.exe -m pip install -r requirements.txt || (echo pip install failed & popd & pause & exit /b 1)
    popd
)

REM ---- Reuse a healthy instance if one is already running (no duplicates) ----
set "PORT="
for /l %%p in (8000,1,8019) do (
    if not defined PORT (
        curl -s -m 1 "http://127.0.0.1:%%p/api/health" 2>nul | findstr /c:"local_token" >nul && set "PORT=%%p"
    )
)
if defined PORT (
    echo [Recall] Already running on port %PORT%, opening it.
    start "" http://127.0.0.1:%PORT%
    exit /b 0
)

REM ---- Pick a free port (prefer 8000, shift if occupied by other projects) ----
for /f %%p in ('backend\.venv\Scripts\python.exe scripts\find_free_port.py') do set "PORT=%%p"
if not defined PORT (
    echo [Recall] No free port in 8000-8019, please close other local services and retry.
    pause
    exit /b 1
)
echo [Recall] Using port %PORT%

REM ---- Start server (backend also serves the built frontend) ----
REM Per-port log file: a stale instance holding the old backend.log can no longer block startup
if not exist logs mkdir logs
start "Recall" /min cmd /c "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port %PORT% --workers 1 --no-access-log >> ..\logs\backend-%PORT%.log 2>&1"

REM ---- Open browser only after THIS server responds (avoids opening another project's page) ----
REM ping-sleep instead of timeout: works even when GNU timeout shadows Windows timeout on PATH
set "READY="
for /l %%i in (1,1,40) do (
    if not defined READY (
        curl -s -m 1 "http://127.0.0.1:%PORT%/api/health" 2>nul | findstr /c:"local_token" >nul && set "READY=1"
        if not defined READY ping 127.0.0.1 -n 2 >nul
    )
)
if not defined READY echo [Recall] Server did not respond in time, opening anyway...
start "" http://127.0.0.1:%PORT%
