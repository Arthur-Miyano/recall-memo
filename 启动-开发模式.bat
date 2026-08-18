@echo off
chcp 65001 >nul
cd /d %~dp0

rem 开发模式：后端 + Vite dev server 各一个窗口，改前端代码热更新
start "Recall 后端" /min cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1"
start "Recall 前端" /min cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 5 /nobreak >nul
start "" http://localhost:5173
