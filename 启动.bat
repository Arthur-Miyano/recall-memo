@echo off
chcp 65001 >nul
cd /d %~dp0

rem 首次运行或前端代码更新后，先构建前端产物
if not exist frontend\dist\index.html (
    echo [Recall] 首次运行，正在构建前端（只需一次）...
    cd frontend
    call npm run build || (echo 前端构建失败 & pause & exit /b 1)
    cd ..
)

rem 启动后端（同时托管前端页面），单独窗口运行，关闭该窗口即停止
start "Recall 记忆助手" /min cmd /c "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1"

rem 等后端起来再开浏览器
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8000
