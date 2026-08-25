# -*- coding: utf-8 -*-
"""记忆树生成 Agent：把标准答案重组为层级大纲（JSON 树），辅助背诵。

要求（与用户约定）：只重组结构，不新增、不删除原文要点——右栏始终展示完整原文，
树只是骨架/导航。输出经 outputs.validate_memory_tree 校验（§4.3），失败受控重试一次。
批量入口一次调用处理多道题（batch prompting），摊薄指令前缀、减少调用次数。
"""
import json
import logging
from typing import Any, Optional

from agents.outputs import validate_memory_tree
from agents.parsing import parse_json_object, extract_json_array
from llm import llm_router
from llm.errors import LLMOutputValidationError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是记忆教练，负责把面试题的标准答案重组为层级大纲，帮助背诵记忆。\n"
    "规则：\n"
    "1. 只重组结构：不新增任何内容，不遗漏原文任何要点；"
    "2. title 是要点的简短名称（不超过 20 字），note 保留原文中的关键短语或数据（原样摘录，不改写）；"
    "3. 层级不超过 4 层，总节点不超过 40 个；并列的要点（如多个模式、多个步骤）应展开为平级子节点；"
    "4. 只输出 JSON，不要输出任何其他文字或 Markdown 代码块；JSON 不带缩进和换行（紧凑格式）。"
)

_SINGLE_USER_TMPL = (
    "题干：{stem}\n\n标准答案：\n{answer}\n\n"
    '输出格式：{{"title": "答案主题", "note": "", "children": ['
    '{{"title": "一级要点", "note": "原文摘句", "children": []}}]}}'
)

_BATCH_USER_TMPL = (
    "下面是多道题的 JSON 数组，请为每道题生成层级大纲。\n"
    "输入：{items}\n\n"
    '输出格式（JSON 数组，与输入一一对应）：[{{"id": 题目id, "tree": {{'
    '"title": "答案主题", "note": "", "children": []}}}}]'
)


async def generate_memory_tree(stem: str, answer: str, budget: Optional[Any] = None) -> dict[str, Any]:
    """单题生成记忆树：校验失败受控重试一次，仍失败抛 LLMOutputValidationError。"""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _SINGLE_USER_TMPL.format(stem=stem, answer=answer)},
    ]
    for attempt in (1, 2):
        if budget is not None:
            budget.before_call(messages)
        _, raw = await llm_router.chat(messages, temperature=0.2)
        tree = validate_memory_tree(parse_json_object(raw))
        if tree is not None:
            return tree
        logger.warning("记忆树输出未通过校验（第 %s 次）：%s", attempt, raw[:200])
    raise LLMOutputValidationError("记忆树输出连续两次未通过校验")


async def generate_memory_trees_batch(
    items: list[dict[str, Any]], budget: Optional[Any] = None
) -> dict[int, dict[str, Any]]:
    """批量生成：一次调用处理多道题，返回 {question_id: tree}。

    items 为 [{"id", "stem", "answer"}]；单题校验失败仅记日志跳过（该题留待下次），
    整批输出无法解析时受控重试一次，仍失败抛 LLMOutputValidationError。
    """
    if not items:
        return {}
    payload = json.dumps(
        [{"id": q["id"], "stem": q["stem"], "answer": q["answer"]} for q in items],
        ensure_ascii=False,
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _BATCH_USER_TMPL.format(items=payload)},
    ]
    rows = None
    for attempt in (1, 2):
        if budget is not None:
            budget.before_call(messages)
        _, raw = await llm_router.chat(messages, temperature=0.2)
        try:
            rows = extract_json_array(raw)
            break
        except (ValueError, json.JSONDecodeError):
            logger.warning("记忆树批量输出无法解析（第 %s 次）：%s", attempt, raw[:200])
    if rows is None:
        raise LLMOutputValidationError("记忆树批量输出连续两次无法解析")

    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        qid = row.get("id")
        tree = validate_memory_tree(row.get("tree"))
        if isinstance(qid, int) and tree is not None:
            result[qid] = tree
        else:
            logger.warning("批量结果中题目 %s 的树未通过校验，跳过", qid)
    return result
