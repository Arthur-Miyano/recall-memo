@echo off
setlocal
cd /d "%~dp0.."

REM ---- First-run setup ----
if not exist frontend\node_modules (
    echo [Recall] First run: installing frontend dependencies...
    pushd frontend
    call npm install || (echo npm install failed & popd & pause & exit /b 1)
    popd
)
if not exist backend\.venv\Scripts\python.exe (
    echo [Recall] First run: creating Python venv and installing backend dependencies...
    pushd backend
    python -m venv .venv || (echo failed to create venv - need Python 3.11+ on PATH & popd & pause & exit /b 1)
    .venv\Scripts\python.exe -m pip install -r requirements.txt || (echo pip install failed & popd & pause & exit /b 1)
    popd
)

REM ---- Dev mode: backend + Vite dev server in separate windows ----
start "Recall backend" /min /d "%~dp0..\backend" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1"
start "Recall frontend" /min /d "%~dp0..\frontend" cmd /k "npm run dev"

set "READY="
for /l %%i in (1,1,20) do (
    if not defined READY (
        curl -s -m 1 http://127.0.0.1:5173/ >nul 2>nul && set "READY=1"
        if not defined READY ping 127.0.0.1 -n 2 >nul
    )
)
if not defined READY (
    echo [Recall] Dev frontend did not become ready. Check the Recall frontend window.
    pause
    exit /b 1
)
if defined RECALL_NO_BROWSER (
    echo [Recall] Browser suppressed for launcher check: http://localhost:5173
) else (
    start "" /b explorer.exe "http://localhost:5173"
)
