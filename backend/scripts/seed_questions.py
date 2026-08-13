# -*- coding: utf-8 -*-
"""一次性种子题库脚本：

1. 读取 docs/python_fullstack_bagu.md，切出 Python 部分的若干小节；
2. 调用 LLM 把每节提炼成一道题（标准题干/标准答案/难度/关键词/标签）；
3. 生成结果写入 data/questions/seed_python.json；
4. 连同手工补充的 vue3 / agent 题一起导入 SQLite。

运行方式（在 backend/ 目录下）：
    .venv/Scripts/python scripts/seed_questions.py            # 全流程（调 LLM）
    .venv/Scripts/python scripts/seed_questions.py --import-only  # 只用已有 JSON 入库
"""
import asyncio
import json
import re
import sys
from pathlib import Path

# 让脚本能直接 import backend/ 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session as DBSession, select

from config import PROJECT_ROOT
from database import engine, init_db
from llm import llm_router
from models import Question

MD_PATH = PROJECT_ROOT / "docs" / "python_fullstack_bagu.md"
SEED_JSON = PROJECT_ROOT / "data" / "questions" / "seed_python.json"

# 控制 API 调用量：只对前 N 个 Python 小节调用 LLM
MAX_LLM_SECTIONS = 10
# 单节材料截断长度，控制 token 消耗
SECTION_CHAR_LIMIT = 3000

_EXTRACT_SYSTEM_PROMPT = (
    "你是技术面试题库编辑。根据给定的技术讲解材料提炼一道面试题，"
    "只输出一个 JSON 对象，不要输出任何其他文字或 Markdown 代码块。"
)

# 手工补充的题目（不消耗 API）
MANUAL_QUESTIONS = [
    {
        "stem": "Vue 3 的响应式原理是什么？ref 和 reactive 有什么区别？",
        "answer": (
            "Vue 3 的响应式基于 ES6 的 Proxy 实现，相比 Vue 2 的 Object.defineProperty，"
            "可以拦截对象的全部操作（新增、删除属性、数组下标修改等），无需递归遍历和特殊 API。"
            "配合 Reflect 做正确的 this 绑定，effect/track/trigger 完成依赖收集与派发更新。"
            "reactive 只能作用于对象类型，返回原对象的响应式代理，解构会丢失响应性；"
            "ref 可以包裹任意类型，通过 .value 访问，内部对对象类型会再交给 reactive 处理。"
            "模板中 ref 会自动解包，JS 中必须写 .value。"
        ),
        "tech_stack": "vue3",
        "difficulty": "medium",
        "keywords": ["Proxy", "ref", "reactive", "依赖收集", "响应式"],
        "tags": ["vue3", "响应式原理"],
    },
    {
        "stem": "Vue 3 中父子组件通信有哪些方式？各自适用什么场景？",
        "answer": (
            "常见方式有五种：1. props / emit：父传子用 props，子传父用 emit 自定义事件，是最基础的方式；"
            "2. v-model：双向绑定场景，可绑定多个 v-model 参数；"
            "3. provide / inject：跨层级祖先向后代传值，适合深层嵌套，但非响应式数据需传 ref；"
            "4. ref / expose：父组件通过 ref 拿到子组件实例，调用其 expose 暴露的方法；"
            "5. 状态管理 Pinia 或事件总线 mitt：跨组件、非父子关系通信。"
            "简单父子通信优先 props/emit，跨层级用 provide/inject，全局共享状态用 Pinia。"
        ),
        "tech_stack": "vue3",
        "difficulty": "basic",
        "keywords": ["props", "emit", "provide/inject", "v-model", "Pinia"],
        "tags": ["vue3", "组件通信"],
    },
    {
        "stem": "什么是 Agent 的 ReAct 模式？它的工作流程是怎样的？",
        "answer": (
            "ReAct（Reasoning + Acting）是让大模型交替进行推理与行动的 Agent 范式。"
            "工作流程是一个循环：模型先输出 Thought（对当前任务的思考与下一步计划），"
            "再输出 Action（调用某个工具及参数），宿主程序执行工具后把 Observation（执行结果）"
            "回灌给模型，模型基于新观察继续下一轮 Thought，直到给出最终答案。"
            "相比纯 Chain-of-Thought，ReAct 把推理轨迹与外部工具调用交织，"
            "既能用推理指导行动，又能用行动结果纠正推理，减少幻觉，是 LangChain 等框架的经典 Agent 模式。"
        ),
        "tech_stack": "agent",
        "difficulty": "medium",
        "keywords": ["ReAct", "Thought", "Action", "Observation", "工具调用"],
        "tags": ["agent", "推理范式"],
    },
    {
        "stem": "Function Calling 的原理是什么？它和 Prompt 工程是什么关系？",
        "answer": (
            "Function Calling 是让大模型以结构化方式调用外部函数的机制："
            "开发者把函数的名称、描述、参数 JSON Schema 随请求一起发给模型，"
            "模型判断需要调用时，不直接执行，而是输出符合 Schema 的结构化参数（tool_calls），"
            "由宿主程序真正执行函数，再把结果作为新消息回灌给模型生成最终回复。"
            "它本质上是'约定俗成的 Prompt 工程 + 模型层的专门训练/微调'："
            "早期靠 Prompt 让模型输出 JSON 再解析，稳定性差；Function Calling 把这个约定内化到模型能力里，"
            "输出更可靠。它是构建 Agent 工具调用能力的基础设施，MCP 等协议也建立在其之上。"
        ),
        "tech_stack": "agent",
        "difficulty": "medium",
        "keywords": ["Function Calling", "tool_calls", "JSON Schema", "工具调用", "MCP"],
        "tags": ["agent", "工具调用"],
    },
]


def split_python_sections(text: str) -> list[tuple[str, str]]:
    """按 `## N. 标题` 一级编号切分 Python 部分的小节，遇到 `## N.M`（Vue 部分）停止。"""
    sections: list[tuple[str, str]] = []
    title: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^## \d+\.\d+", line):
            break  # 进入 Vue 等二级编号部分，Python 部分结束
        m = re.match(r"^## (\d+)\.\s+(.+)$", line)
        if m:
            if title is not None:
                sections.append((title, "\n".join(lines).strip()))
            title, lines = m.group(2).strip(), []
        elif title is not None:
            lines.append(line)
    if title is not None:
        sections.append((title, "\n".join(lines).strip()))
    return sections


async def extract_question(title: str, content: str) -> dict:
    """调用 LLM 把一个小节提炼成一道题。"""
    user_prompt = (
        f"下面是关于「{title}」的技术讲解材料：\n\n"
        f"{content[:SECTION_CHAR_LIMIT]}\n\n"
        "请把它提炼成一道面试题，输出 JSON，字段如下：\n"
        '- stem：标准题干，一句面试提问（如"请讲讲……"）；\n'
        "- answer：标准答案，覆盖材料中的核心考点，200~400 字，条理清晰；\n"
        "- difficulty：basic / medium / hard 三选一；\n"
        "- keywords：3~6 个关键词数组；\n"
        "- tags：2~4 个标签数组。\n"
        "只输出 JSON 对象本身。"
    )
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    provider, raw = await llm_router.chat(messages, temperature=0.3)
    match = re.search(r"\{.*\}", raw.strip(), flags=re.DOTALL)
    if not match:
        raise ValueError(f"小节「{title}」提炼结果不含 JSON")
    data = json.loads(match.group(0))
    return {
        "stem": str(data["stem"]).strip(),
        "answer": str(data["answer"]).strip(),
        "tech_stack": "python",
        "difficulty": str(data.get("difficulty", "medium")),
        "keywords": [str(k) for k in data.get("keywords", [])],
        "tags": [str(t) for t in data.get("tags", [])],
        "source_section": title,
    }


async def generate_python_seeds() -> list[dict]:
    """切分 md 并逐节调用 LLM 提炼题目。"""
    text = MD_PATH.read_text(encoding="utf-8")
    sections = split_python_sections(text)[:MAX_LLM_SECTIONS]
    print(f"切分出 {len(sections)} 个 Python 小节，将调用 LLM 提炼")
    seeds = []
    for i, (title, content) in enumerate(sections, 1):
        print(f"[{i}/{len(sections)}] 提炼：{title}")
        seed = await extract_question(title, content)
        seeds.append(seed)
    return seeds


def import_questions(items: list[dict]) -> None:
    """入库：按题干去重，已存在则跳过，保证脚本可重复运行。"""
    init_db()
    inserted, skipped = 0, 0
    with DBSession(engine) as db:
        for item in items:
            exists = db.exec(select(Question).where(Question.stem == item["stem"])).first()
            if exists:
                skipped += 1
                continue
            db.add(
                Question(
                    stem=item["stem"],
                    answer=item["answer"],
                    tech_stack=item["tech_stack"],
                    difficulty=item.get("difficulty", "medium"),
                    keywords=item.get("keywords", []),
                    tags=item.get("tags", []),
                )
            )
            inserted += 1
        db.commit()
        total = len(db.exec(select(Question)).all())
    print(f"入库完成：新增 {inserted} 道，跳过 {skipped} 道（重复），库内共 {total} 道")


async def main() -> None:
    import_only = "--import-only" in sys.argv

    if import_only:
        python_seeds = json.loads(SEED_JSON.read_text(encoding="utf-8"))
        print(f"从 {SEED_JSON.name} 读入 {len(python_seeds)} 道 Python 题")
    else:
        python_seeds = await generate_python_seeds()
        SEED_JSON.parent.mkdir(parents=True, exist_ok=True)
        SEED_JSON.write_text(json.dumps(python_seeds, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {SEED_JSON}")

    import_questions([*python_seeds, *MANUAL_QUESTIONS])


if __name__ == "__main__":
    asyncio.run(main())
