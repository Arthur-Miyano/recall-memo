# -*- coding: utf-8 -*-
"""评分 Agent：结构化评分 JSON + difflib 反背诵检测。"""
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

from models import Question

from .base import BaseAgent

logger = logging.getLogger(__name__)

# 维度权重，见文档 2.4：准确性 50% / 逻辑 30% / 自然度 20%
WEIGHT_ACCURACY = 0.5
WEIGHT_LOGIC = 0.3
WEIGHT_NATURALNESS = 0.2

# 反背诵判定阈值：整段字符重合率 > 0.3 判为背诵痕迹
RECITE_RATIO_THRESHOLD = 0.3

_SCORE_SYSTEM_PROMPT = (
    "你是严格的技术面试评分专家。根据用户回答对照标准答案进行评分，"
    "只输出一个 JSON 对象，不要输出任何其他文字、解释或 Markdown 代码块。"
)


def _clamp(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    """把得分收敛到 [low, high] 区间的浮点数。"""
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return low


class GraderAgent(BaseAgent):
    """评分 Agent：准确性/逻辑由 LLM 评，自然度由 difflib 结果约束 LLM 输出。"""

    name = "评分"

    async def run(self, question: Question, user_answer: str) -> dict[str, Any]:
        """主入口：对一条回答输出结构化评分。"""
        return await self.score(question, user_answer)

    @staticmethod
    def detect_reciting(user_answer: str, standard_answer: str) -> tuple[float, bool]:
        """反背诵检测：返回 (整段字符重合率, 是否背诵痕迹)。"""
        ratio = SequenceMatcher(None, user_answer, standard_answer).ratio()
        return ratio, ratio > RECITE_RATIO_THRESHOLD

    async def score(self, question: Question, user_answer: str) -> dict[str, Any]:
        """输出结构化评分：各维度得分、总分、是否背诵、遗漏关键点、定性点评。"""
        ratio, is_reciting = self.detect_reciting(user_answer, question.answer)

        naturalness_rule = (
            "该回答已被判定有背诵痕迹（与标准答案逐字重合率过高），naturalness 必须给 0~5 分。"
            if is_reciting
            else "该回答重合率正常，naturalness 按表达是否自然、口语化程度在 0~100 评分。"
        )
        user_prompt = (
            f"【面试题】{question.stem}\n\n"
            f"【标准答案】{question.answer}\n\n"
            f"【题目关键词】{'、'.join(question.keywords or [])}\n\n"
            f"【用户回答】{user_answer}\n\n"
            f"【反背诵检测】用户回答与标准答案的整段字符重合率为 {ratio:.1%}，"
            f"{'超过' if is_reciting else '未超过'} 30% 阈值。\n\n"
            "请按以下维度评分（均为 0~100 的数字）：\n"
            "1. accuracy：核心考点准确性，是否覆盖标准答案的关键技术点；\n"
            "2. logic：逻辑清晰度，回答结构是否条理分明；\n"
            f"3. naturalness：表达自然度。{naturalness_rule}\n"
            "另外给出：\n"
            '- missed_points：遗漏的关键点列表（字符串数组，无遗漏则为空数组）；\n'
            '- comment：100 字以内的定性点评。\n\n'
            '输出格式：{"accuracy": 数字, "logic": 数字, "naturalness": 数字, '
            '"missed_points": ["..."], "comment": "..."}'
        )
        messages = [
            {"role": "system", "content": _SCORE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        _, content = await self.llm.chat(messages, temperature=0.2)
        parsed = self._parse_json(content)

        accuracy = _clamp(parsed.get("accuracy"))
        logic = _clamp(parsed.get("logic"))
        naturalness = _clamp(parsed.get("naturalness"))
        # 背诵痕迹：无论 LLM 输出如何，自然度强制压到 0~5 分（文档 2.4）
        if is_reciting:
            naturalness = min(naturalness, 5.0)

        total = round(
            accuracy * WEIGHT_ACCURACY + logic * WEIGHT_LOGIC + naturalness * WEIGHT_NATURALNESS,
            1,
        )
        missed = parsed.get("missed_points")
        if not isinstance(missed, list):
            missed = []
        return {
            "accuracy": accuracy,
            "logic": logic,
            "naturalness": naturalness,
            "total": total,
            "is_reciting": is_reciting,
            "similarity": round(ratio, 4),
            "missed_points": [str(p) for p in missed],
            "comment": str(parsed.get("comment", "")),
        }

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """从模型输出中稳健地提取 JSON 对象（容忍代码块围栏与前后杂文本）。"""
        text = content.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            logger.warning("评分输出中未找到 JSON：%s", content[:200])
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("评分 JSON 解析失败：%s", content[:200])
            return {}
        return data if isinstance(data, dict) else {}
