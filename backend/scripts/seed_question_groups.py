# -*- coding: utf-8 -*-
"""一次性追问组种子脚本（Phase 3 测试备数据，正式的"人工绑定界面"在 Phase 5）。

从现有题库中按题干关键词定位同一知识点的递进题，写入 question_groups 表：
- Agent 方向：ReAct 模式 → Function Calling（从推理范式追问到底层机制）
- Python 方向：元类 → MRO（从类的创建追问到多继承解析顺序）

运行方式（在 backend/ 目录下，可重复运行，按组名去重）：
    .venv/Scripts/python scripts/seed_question_groups.py
"""
import sys
from pathlib import Path

# 让脚本能直接 import backend/ 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session as DBSession, select

from database import engine, init_db
from models import Question, QuestionGroup

# (组名, [题干关键词，按递进顺序])
GROUP_DEFS = [
    ("Agent 推理范式与工具调用", ["ReAct", "Function Calling"]),
    ("Python 类机制进阶", ["元类", "MRO"]),
]


def main() -> None:
    init_db()
    with DBSession(engine) as db:
        questions = list(db.exec(select(Question)).all())
        for name, keywords in GROUP_DEFS:
            ids: list[int] = []
            for kw in keywords:
                match = next((q for q in questions if kw in q.stem), None)
                if match is None:
                    print(f"[跳过] 组「{name}」未找到含「{kw}」的题目")
                    break
                ids.append(match.id)
            else:
                exists = db.exec(select(QuestionGroup).where(QuestionGroup.name == name)).first()
                if exists:
                    exists.question_ids = ids
                    db.add(exists)
                    print(f"[更新] 组「{name}」→ {ids}")
                else:
                    db.add(QuestionGroup(name=name, question_ids=ids))
                    print(f"[新增] 组「{name}」→ {ids}")
        db.commit()
        total = len(db.exec(select(QuestionGroup)).all())
    print(f"完成，库内共 {total} 个追问组")


if __name__ == "__main__":
    main()
