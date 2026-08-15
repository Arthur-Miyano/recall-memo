# Recall · 记忆助手

本地单机运行的程序员八股背诵训练工具：录入题库后，以记忆训练 / 模拟面试 / 终局复盘三种模式循环巩固，附知识图谱与统计仪表盘。

## 架构

- 后端：FastAPI + SQLite（`backend/`，数据库文件在 `data/bagu.db`）
- 前端：Vue 3 + Vite（`frontend/`，纸墨 / 墨水屏风格）

## 启动步骤

### 1. 后端（端口 8000）

```bash
python -m venv backend/.venv
source backend/.venv/Scripts/activate   # Windows Git Bash；CMD 用 backend\.venv\Scripts\activate
pip install -r backend/requirements.txt
```

在项目**根目录**新建 `.env`（后端从这里读取，见 `backend/config.py`）：

```ini
DEEPSEEK_API_KEY=sk-...   # 必填：LLM 出题 / 评分 / 助理对话
KIMI_API_KEY=sk-...       # 可选：作为备用 Provider，按 LLM_PROVIDER_PRIORITY 顺序兜底
```

> 红线：`.env` 已被 `.gitignore` 排除，API Key 不出本机，不要提交、不要截图外发。

启动（在 `backend/` 目录下）：

```bash
cd backend
uvicorn main:app --port 8000
```

### 2. 前端（端口 5173）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。端口约定：后端 8000，前端 5173（前端 api 层写死 `http://localhost:8000`）。

### 3. 录入题库

启动后进入「仪表盘 → 录入题库」，支持粘贴文本或上传 md / txt / json / pdf 文件（PDF 由后端提取文本）。

## 目录说明

- `backend/` — FastAPI 应用（api 路由 / agents 出题评分 / llm Provider 封装 / models）
- `frontend/` — Vue 3 单页应用（views 页面 / components / api 接口层 / mock 演示数据）
- `data/questions/` — 题库源文件；`docs/` — 参考资料
- 后端不可达时前端会回退内置演示数据，并显示「离线模式 · 演示数据」角标
