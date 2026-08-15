# -*- coding: utf-8 -*-
"""面试官 Agent：题干变体生成（面试官口吻重述），记忆训练模式下逐题出题。"""
from sqlmodel import Session as DBSession

from models import Question

from .base import BaseAgent

# 变体缓存上限：只保留最近 N 条。
# 原因有二：1) 防止 Question.variants JSON 列无限膨胀（读写都随之变慢）；
#          2) 历史变体会全量注入 prompt，无上限会把 prompt 撑长、摊薄避重效果。
MAX_STORED_VARIANTS = 8

# 变体生成的系统提示词：约束修改幅度与技术内核
_VARIANT_SYSTEM_PROMPT = (
    "你是一位经验丰富的技术面试官，正在对候选人进行口头提问。"
    "你的任务是把给定的标准题干改写成自然的面试官口吻提问。"
    "约束：\n"
    "1. 修改幅度不超过 40%：保留题干的核心措辞与关键技术词，只做口吻化、口语化改写；\n"
    "2. 技术内核和考察范围完全不变，不得新增或删减考点；\n"
    "3. 像真实面试官一样自然提问，可加简短铺垫（如「能聊聊……吗」），但不要寒暄过多；\n"
    "4. 只输出提问本身，不要输出答案、解释或任何额外内容。"
)


class InterviewerAgent(BaseAgent):
    """面试官 Agent：生成变体题干并缓存，保证同一题每次提问方式不同。"""

    name = "面试官"

    async def run(self, question: Question, db: DBSession) -> str:
        """主入口：为一道题生成新的变体题干。"""
        return await self.generate_variant(question, db)

    async def generate_variant(self, question: Question, db: DBSession) -> str:
        """基于原始题干生成面试官口吻的变体题干。

        - 已用过的变体（仅最近 MAX_STORED_VARIANTS 条）会注入 prompt，要求模型避免重复；
        - 生成结果追加到 Question.variants 缓存入库（超出上限丢弃最旧的），下次生成时继续避重。
        """
        used = list(question.variants or [])
        used_text = "\n".join(f"- {v}" for v in used) if used else "（暂无）"
        user_prompt = (
            f"【标准题干】{question.stem}\n\n"
            f"【该题已使用过的提问方式，请避开这些表达】\n{used_text}\n\n"
            "请生成一个新的面试官口吻变体题干："
        )
        messages = [
            {"role": "system", "content": _VARIANT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        # 温度调高，增加每次提问方式的差异
        _, content = await self.llm.chat(messages, temperature=0.9)
        variant = content.strip().strip('"')

        # 缓存变体到题库表（整体重新赋值，触发 JSON 列更新）；只保留最近 N 条，
        # 防止 variants 无限膨胀：既避免 JSON 列越写越大，也避免 prompt 注入的历史变体越积越长
        question.variants = [*used, variant][-MAX_STORED_VARIANTS:]
        db.add(question)
        db.commit()
        return variant
