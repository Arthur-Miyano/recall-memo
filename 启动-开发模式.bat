@echo off
setlocal
cd /d %~dp0

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
start "Recall backend" /min cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1"
start "Recall frontend" /min cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 5 /nobreak >nul
start "" http://localhost:5173
