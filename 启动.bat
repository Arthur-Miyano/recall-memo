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

REM ---- Start server (backend also serves the built frontend) ----
start "Recall" /min cmd /c "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1"

REM ---- Open browser after the server is up ----
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8000
