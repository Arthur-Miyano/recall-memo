@echo off
setlocal
cd /d "%~dp0.."

REM ---- First-run setup: frontend deps + build ----
if not exist frontend\node_modules (
    echo [Recall] First run: installing frontend dependencies...
    pushd frontend
    call npm install || (popd & call :fail "npm install failed" & exit /b 1)
    popd
)
if not exist frontend\dist\index.html (
    echo [Recall] Building frontend...
    pushd frontend
    call npm run build || (popd & call :fail "frontend build failed" & exit /b 1)
    popd
)

REM ---- First-run setup: backend venv + deps ----
if not exist backend\.venv\Scripts\python.exe (
    echo [Recall] First run: creating Python venv and installing backend dependencies...
    pushd backend
    python -m venv .venv || (popd & call :fail "failed to create venv - need Python 3.11+ on PATH" & exit /b 1)
    .venv\Scripts\python.exe -m pip install -r requirements.txt || (popd & call :fail "pip install failed" & exit /b 1)
    popd
)

if not exist logs mkdir logs
call :find_healthy
if defined PORT (
    echo [Recall] Already running on port %PORT%, opening it.
    call :open_browser
    exit /b 0
)

REM ---- Serialize cold starts so two clicks cannot select the same free port ----
set "LOCKDIR=logs\launcher.lock"
2>nul mkdir "%LOCKDIR%"
if errorlevel 1 (
    echo [Recall] Another launcher is starting the service. Waiting for it...
    for /l %%i in (1,1,30) do (
        call :find_healthy
        if defined PORT goto :ready_from_other_launcher
        ping 127.0.0.1 -n 2 >nul
    )
    call :fail "another startup did not become ready; see logs\launcher.log"
    exit /b 1
)
set "LOCK_HELD=1"

REM Check again after taking the lock: another launcher may have finished just before it.
call :find_healthy
if defined PORT goto :ready

REM ---- Pick a free port (prefer 8000, shift if occupied by other projects) ----
for /f %%p in ('backend\.venv\Scripts\python.exe scripts\find_free_port.py') do set "PORT=%%p"
if not defined PORT (
    call :fail "no free port in 8000-8019; close another local service and retry"
    exit /b 1
)
echo [Recall] Using port %PORT%

REM ---- Start server detached. start /b would let uvicorn inherit this
REM launcher's launcher.log handle and lock it for the server's lifetime ----
backend\.venv\Scripts\python.exe scripts\start_server.py %PORT%

REM ---- Open browser only after THIS server responds ----
set "READY="
for /l %%i in (1,1,20) do (
    if not defined READY (
        curl -s -m 1 "http://127.0.0.1:%PORT%/api/health" 2>nul | findstr /c:"local_token" >nul && set "READY=1"
        if not defined READY ping 127.0.0.1 -n 2 >nul
    )
)
if not defined READY (
    call :fail "server did not become ready; see logs\backend-%PORT%.log"
    exit /b 1
)

:ready
if defined LOCK_HELD rmdir "%LOCKDIR%" 2>nul
echo [Recall] Server is ready on port %PORT%.
call :open_browser
exit /b 0

:ready_from_other_launcher
echo [Recall] Server is ready on port %PORT%.
call :open_browser
exit /b 0

:find_healthy
set "PORT="
for /f %%p in ('backend\.venv\Scripts\python.exe scripts\find_healthy_port.py') do set "PORT=%%p"
exit /b 0

:open_browser
if defined RECALL_NO_BROWSER (
    echo [Recall] Browser suppressed for launcher check: http://127.0.0.1:%PORT%
) else (
    REM Explorer 负责按系统默认浏览器分派 URL；直接用 cmd start URL 在部分 Windows 环境会阻塞启动器。
    start "" /b explorer.exe "http://127.0.0.1:%PORT%"
)
exit /b 0

:fail
set "FAIL_MESSAGE=%~1"
if defined LOCK_HELD rmdir "%LOCKDIR%" 2>nul
echo [Recall] ERROR: %FAIL_MESSAGE%
if not defined RECALL_NO_BROWSER start "" notepad.exe "%~dp0..\logs\launcher.log"
exit /b 1
