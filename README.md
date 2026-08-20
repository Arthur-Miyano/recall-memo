# Recall · 记忆助手

一个本地运行的八股背诵工具，FastAPI + Vue 3，数据存在本机 SQLite。
可以录入自己的题库，用记忆训练、面试模拟、回忆三种模式背题，AI 负责判分和复盘。

## 为什么写这个

就是为了准备面试开始背诵八股，所以写了这个小东西，方便记忆和补错。
看八股的时候觉得都会，被问到就答不上来，所以工具里加了"考"的环节：
出题、判分、追问、复盘都交给 AI，答错的题自动进待补答队列，后面优先重背。

## 界面

整体是纸墨风格，图表是手绘 SVG，没有用图表库。

![首页](docs/screenshots/01-home.png)

首页三个入口：记忆训练、面试模拟、回忆模式（按遗忘规律挑出快忘的题）。
选好技术栈和题量就可以开始。

![记忆训练](docs/screenshots/02-memorize.png)

记忆训练先给题干和标准答案，确认记好了以后打乱顺序开考，题干会换成面试官口吻的说法。
每答一题立刻出分，分准确性、逻辑、自然度三个维度。
如果回答和标准答案逐字重合度太高，会被判成背诵痕迹，自然度直接压低。

![面试模拟](docs/screenshots/07-interview.png)

面试模拟限时两分钟一题，过程中不反馈对错，全部答完才出复盘报告。
答错会进入待补答队列，跳过直接判负。

![终局复盘](docs/screenshots/06-review.png)

复盘报告逐题对照你的回答和标准答案，遗漏的要点会标出来，
另外给出薄弱点分析和复习建议。

![题库总览](docs/screenshots/03-bank.png)

题库按技术栈和知识点两级分组，每个知识点一格，背过就涂黑。
内置 174 题（Python / Agent / 数据库 / Vue3），也可以导入自己的资料。
技术栈分类覆盖了 21 个常见方向（Java / Go / C / C++ / 前端框架 / 网络 / 操作系统 / 算法 / 分布式这些都在），
清单外的 AI 会自己命名一个分类，不会硬塞进别的组。
题格上悬停可以改题、删题；「迁移题目」模式可以多选一批题整体搬到别的分组——
导入时分类标错了就靠它救回来。

![录入题库](docs/screenshots/08-import.png)

录入支持粘贴文本，也支持上传 md / txt / json / pdf，可以多选。
整篇八股文档可以直接扔进去，LLM 会提取里面真正的面试题，
缺答案的自动补全，重复的自动跳过。录入在后台执行，关页面不影响，重新打开能接着看进度。

![仪表盘](docs/screenshots/04-dashboard.png)

仪表盘包括每日背诵记录、答题趋势、各技术栈正确率、知识图谱和 API 消耗统计。
每次 LLM 调用的 token 和估算费用都有记录，失败的调用也会记账。

![笔记](docs/screenshots/05-notes.png)

背诵时选中句子，右键可以存进笔记，相关的知识点可以记到一起。

右下角的螃蟹是智能助手，可以问它背诵情况、让它给复习建议。
它也能直接干活：跟它说"删掉第几题""把 Redis 的题迁到数据库"，它会列出要做的操作，
你点确认才执行，不会偷偷动你的题库。

## 运行

需要 Python 3.11+ 和 Node 18+。

Windows 下最简单的办法：装好后端依赖（见下）之后，双击根目录的 `启动.bat`，
它会自动起服务并打开浏览器，前后端一个进程搞定。
`启动-开发模式.bat` 是改代码用的（前后端分开跑，前端热更新）。

手动方式如下。

**1. 后端（端口 8000）**

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash；CMD 用 .venv\Scripts\activate
pip install -r requirements.txt
```

在项目**根目录**新建 `.env`：

```ini
DEEPSEEK_API_KEY=sk-...   # 必填：出题 / 判分 / 助理对话
KIMI_API_KEY=sk-...       # 可选：备用 Provider，DeepSeek 不可用时自动切换
# ZHIPU_API_KEY=...       # 可选：智谱（bigmodel.cn），想用就在设置面板里切
# DOUBAO_API_KEY=...      # 可选：豆包（火山方舟），模型名可填 ep- 开头的推理接入点 ID
```

```bash
cd backend
uvicorn main:app --port 8000
```

**2. 前端（端口 5173）**

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。

## API Key 配置

两种方式：

- 写进根目录的 `.env`；
- 或者在「仪表盘 → 模型与密钥配置」页面里填，效果一样（也是写回 `.env`）。

![设置面板](docs/screenshots/09-settings.png)

DeepSeek 目前有两种模型：DeepSeek V4 flash 和 DeepSeek V4 PRO。推荐使用 flash，默认就是它。
另外 DeepSeek 分峰谷时段计价，北京时间 9-12 点、14-18 点是高峰，其余时间半价，
批量导入题库可以放在非高峰跑。

> Key 只保存在本机 `.env`，接口只返回掩码，不写日志、不进 localStorage。
> `.env` 已在 `.gitignore` 里，但自己注意不要截图外发。

## 升级与数据迁移

所有数据都在 `data/bagu.db` 这一个文件里，`data/` 已在 `.gitignore`，
所以 `git pull` 原地升级不会动你的题库和背诵记录，直接拉就行。

换新电脑或全新下载的话：旧环境打开「仪表盘 → 数据备份与迁移」点导出，
把下载的 `.db` 文件拿到新环境同一个面板导入，题库、背诵记录、笔记全部带过来。
导入前会自动把当前数据备份成 `data/bagu.db.bak-时间戳`，
同一份文件重复导入也不会产生重复数据。

## 使用流程

1. 仪表盘 → 录入题库，上传文件或粘贴文本；
2. 首页 → 记忆训练，先背后考，每题即时出分；
3. 首页 → 面试模拟，限时作答，结束出复盘报告；
4. 答错的题自动进待补答队列，下次记忆训练优先重背；
5. 背诵时把好句子右键存进笔记；
6. 仪表盘查看正确率走势和 API 消耗。

## 技术栈

- 后端：FastAPI + SQLModel（SQLite），6 个 Agent 分工（总控 / 面试官 / 评分 / 策略 / 助理 / 录入清洗）
- 前端：Vue 3 + Vite，无 UI 框架，图表手绘 SVG
- LLM：DeepSeek / Kimi 双 Provider，失败自动切换

## 目录

```
backend/    FastAPI 应用（api 路由 / agents / llm 封装 / models / tests）
frontend/   Vue 3 单页应用（views / components / api / mock 演示数据）
data/       SQLite 库和题库源文件（本地数据，不进 git）
docs/       需求文档、方案设计、页面截图
```

后端测试：`cd backend && pytest tests/ -q`（286 项）

## 备注

- 语音输入没有内置。想练口述作答，可以用腾讯输入法或豆包输入法的语音输入，直接对着答题框说。
- 后端没启动时，前端会回退到内置演示数据，左下角显示"离线模式"，不会白屏。

## License

MIT
