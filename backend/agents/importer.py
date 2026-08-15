# -*- coding: utf-8 -*-
"""题库录入清洗器（stateless，不落库）：

职责：
1. 解析用户提供的原始文本/JSON 为结构化题目条目；
2. 纯文本解析不出的片段，交给 LLM 做结构化提取（一次调用提取多题）；
3. 对缺标准答案 / 缺技术栈分类的条目，批量调 LLM 补全；
4. 提供题干文本相似度（difflib + 字符 bigram Jaccard 取较大值），供入库前去重。

数据流：api/bank.py 的 POST /api/bank/import 调用本模块，
解析 → LLM 提取（兜底）→ LLM 补全 → 相似度去重 → 写 Question 表。
"""
import json
import re
from difflib import SequenceMatcher
from typing import Any, Optional

from llm import llm_router
from llm.router import LLMProviderUnavailableError

# 题干相似度阈值：>= 该值视为重复，跳过入库
SIMILARITY_THRESHOLD = 0.85

# 允许的技术栈分类（与种子题库约定一致）
ALLOWED_STACKS = {"python", "agent", "vue3"}

# 用户手填技术栈的常见别名 → 规范 key
_STACK_ALIASES = {
    "py": "python", "python": "python", "python3": "python",
    "vue": "vue3", "vue3": "vue3", "vue 3": "vue3", "vuejs": "vue3", "前端": "vue3",
    "agent": "agent", "agents": "agent", "智能体": "agent", "大模型": "agent", "llm": "agent",
}

# 题内字段标签行：答案：/ 技术栈：/ 知识点：（兼容半角冒号与英文 key）
_LABEL_PATTERNS = {
    "answer": re.compile(r"^\s*(?:答案|answer)\s*[:：]\s*(.*)$", re.IGNORECASE),
    "tech_stack": re.compile(r"^\s*(?:技术栈|tech[_ ]?stack)\s*[:：]\s*(.*)$", re.IGNORECASE),
    "knowledge_point": re.compile(r"^\s*(?:知识点|knowledge[_ ]?point)\s*[:：]\s*(.*)$", re.IGNORECASE),
}

# 多题分隔：单独的 ---（或更多 -）一行，或空行分段
_CHUNK_SPLIT = re.compile(r"^\s*-{3,}\s*$", re.MULTILINE)

_EXTRACT_SYSTEM = (
    "你是技术面试题库编辑。把用户给的原始文本整理成结构化面试题，"
    "只输出一个 JSON 数组，不要输出任何其他文字或 Markdown 代码块。"
)

_ENRICH_SYSTEM = (
    "你是技术面试题库编辑。为给定的面试题补全缺失字段，"
    "只输出一个 JSON 数组，不要输出任何其他文字或 Markdown 代码块。"
)


def normalize_stack(raw: Optional[str]) -> Optional[str]:
    """技术栈归一化：别名映射 + 白名单校验，无法识别返回 None（交给 LLM 分类）。"""
    if not raw:
        return None
    key = str(raw).strip().lower()
    return _STACK_ALIASES.get(key) or (key if key in ALLOWED_STACKS else None)


def _norm_text(s: str) -> str:
    """题干归一化：小写、去标点与空白，让相似度不受格式差异影响。"""
    return re.sub(r"[\s　，。、？?！!：:；;（）()【】\[\]「」\"'“”‘’…—\-_.]", "", s.lower())


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def stem_similarity(a: str, b: str) -> float:
    """两个题干的文本相似度（0~1）：SequenceMatcher 与字符 bigram Jaccard 取较大值。

    项目没有向量库/embedding，用纯文本相似度近似"语义重复"。
    """
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ga, gb = _bigrams(na), _bigrams(nb)
    jaccard = len(ga & gb) / len(ga | gb)
    return max(ratio, jaccard)


def _parse_chunk(chunk: str) -> Optional[dict[str, Any]]:
    """规则解析一个题目片段：标签行抽字段，其余行拼题干。无题干返回 None。"""
    item: dict[str, Any] = {}
    stem_lines: list[str] = []
    answer_lines: list[str] = []
    in_answer = False  # "答案："行之后到下一个标签行之间的内容都算答案
    for line in chunk.splitlines():
        matched = False
        for field, pat in _LABEL_PATTERNS.items():
            m = pat.match(line)
            if m:
                matched = True
                in_answer = field == "answer"
                value = m.group(1).strip()
                if value:
                    if field == "answer":
                        answer_lines.append(value)
                    else:
                        item[field] = value
                break
        if matched:
            continue
        if line.strip():
            (answer_lines if in_answer else stem_lines).append(line.strip())
    stem = "\n".join(stem_lines).strip()
    if not stem:
        return None
    item["stem"] = stem
    if answer_lines:
        item["answer"] = "\n".join(answer_lines).strip()
    return item


def parse_text(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """把用户输入解析成题目条目列表。

    返回 (items, leftovers)：
    - items：规则/JSON 直接解析出的条目（可能仍缺 answer / tech_stack，后续补全）；
    - leftovers：规则解析不出的原始片段，留给 LLM 结构化提取。
    """
    text = text.strip()
    if not text:
        return [], []

    # JSON 输入：[{question, answer, tech_stack, knowledge_point}, ...]
    if text.startswith("["):
        try:
            raw_items = json.loads(text)
            items = []
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                stem = str(raw.get("question") or raw.get("stem") or "").strip()
                if not stem:
                    continue
                item: dict[str, Any] = {"stem": stem}
                for src, dst in (("answer", "answer"), ("tech_stack", "tech_stack"),
                                 ("knowledge_point", "knowledge_point")):
                    value = raw.get(src)
                    if value:
                        item[dst] = str(value).strip()
                items.append(item)
            return items, []
        except json.JSONDecodeError:
            # 形如 JSON 但解析失败：整体交给 LLM 提取
            return [], [text]

    # 纯文本：先按 --- 切，再在每个分块内按空行切段
    items, leftovers = [], []
    for block in _CHUNK_SPLIT.split(text):
        for chunk in re.split(r"\n\s*\n", block):
            chunk = chunk.strip()
            if not chunk:
                continue
            parsed = _parse_chunk(chunk)
            (items if parsed else leftovers).append(parsed or chunk)
    return items, leftovers


def _extract_json_array(raw: str) -> list[dict]:
    """从 LLM 回复里抠出 JSON 数组（容忍前后多余文字/代码块）。"""
    match = re.search(r"\[.*\]", raw.strip(), flags=re.DOTALL)
    if not match:
        raise ValueError("LLM 回复中不含 JSON 数组")
    data = json.loads(match.group(0))
    return [d for d in data if isinstance(d, dict)]


async def llm_extract(chunks: list[str]) -> list[dict[str, Any]]:
    """LLM 结构化提取：把规则解析不出的片段一次调用整理成题目条目。"""
    if not chunks:
        return []
    numbered = "\n\n".join(f"【片段 {i + 1}】\n{c[:2000]}" for i, c in enumerate(chunks))
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM},
        {"role": "user", "content": (
            "下面是从用户录入文本中切出的若干片段，请把每个片段整理成一道面试题。\n"
            "输出 JSON 数组，每个元素字段：\n"
            "- stem：标准题干，一句面试提问；\n"
            "- answer：片段里给出的答案（没有就留空字符串）；\n"
            "- tech_stack：python / agent / vue3 三选一（判断不了就留空字符串）；\n"
            "- knowledge_point：知识点短语（如 装饰器、响应式原理）。\n\n"
            f"{numbered}\n\n只输出 JSON 数组本身。"
        )},
    ]
    _, raw = await llm_router.chat(messages, temperature=0.2)
    items = []
    for d in _extract_json_array(raw):
        stem = str(d.get("stem") or "").strip()
        if not stem:
            continue
        item: dict[str, Any] = {"stem": stem}
        for field in ("answer", "tech_stack", "knowledge_point"):
            value = str(d.get(field) or "").strip()
            if value:
                item[field] = value
        items.append(item)
    return items


async def llm_enrich(items: list[dict[str, Any]]) -> list[dict[str, list[str]]]:
    """LLM 批量补全：为缺 answer 或缺 tech_stack 的条目生成标准答案与分类。

    返回与 items 等长的列表，每项是该题被 AI 补全的字段名列表（可能为空）。
    调用失败抛 LLMProviderUnavailableError，由调用方降级处理。
    """
    need = [i for i, it in enumerate(items)
            if not it.get("answer") or not normalize_stack(it.get("tech_stack"))]
    enriched: list[dict[str, list[str]]] = [{"fields": []} for _ in items]
    if not need:
        return enriched

    payload = []
    for i in need:
        it = items[i]
        payload.append({
            "index": len(payload),
            "stem": it["stem"],
            "answer": it.get("answer") or "",
            "tech_stack": it.get("tech_stack") or "",
            "knowledge_point": it.get("knowledge_point") or "",
        })
    messages = [
        {"role": "system", "content": _ENRICH_SYSTEM},
        {"role": "user", "content": (
            "下面是若干面试题（JSON 数组），请为每题补全缺失字段：\n"
            "- answer 为空时：生成标准答案，150~350 字，条理清晰，覆盖核心考点；\n"
            "- tech_stack 为空时：按内容归入 python / agent / vue3 之一；\n"
            "- knowledge_point 为空时：给一个知识点短语（如 装饰器、GIL、响应式原理）；\n"
            "- 另给出 keywords：3~5 个关键词数组，以及 difficulty：basic / medium / hard。\n"
            "已有字段保持原样不要改写。输出 JSON 数组，每个元素带原 index 与全部字段。\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n\n只输出 JSON 数组本身。"
        )},
    ]
    _, raw = await llm_router.chat(messages, temperature=0.3)
    for d in _extract_json_array(raw):
        try:
            src = need[int(d.get("index", -1))]
        except (ValueError, IndexError):
            continue
        it = items[src]
        fields: list[str] = []
        if not it.get("answer") and str(d.get("answer") or "").strip():
            it["answer"] = str(d["answer"]).strip()
            fields.append("answer")
        if not normalize_stack(it.get("tech_stack")):
            stack = normalize_stack(str(d.get("tech_stack") or ""))
            if stack:
                it["tech_stack"] = stack
                fields.append("tech_stack")
        if not it.get("knowledge_point") and str(d.get("knowledge_point") or "").strip():
            it["knowledge_point"] = str(d["knowledge_point"]).strip()
            fields.append("knowledge_point")
        # keywords / difficulty 只在 LLM 给了且本地没有时采纳（本地从不预填，故给了就采纳）
        keywords = d.get("keywords")
        if isinstance(keywords, list) and keywords:
            it["keywords"] = [str(k) for k in keywords][:6]
            fields.append("keywords")
        difficulty = str(d.get("difficulty") or "").strip()
        if difficulty in ("basic", "medium", "hard"):
            it["difficulty"] = difficulty
            fields.append("difficulty")
        enriched[src]["fields"] = fields
    return enriched


__all__ = [
    "SIMILARITY_THRESHOLD", "ALLOWED_STACKS", "normalize_stack", "stem_similarity",
    "parse_text", "llm_extract", "llm_enrich", "LLMProviderUnavailableError",
]
