# -*- coding: utf-8 -*-
"""批量生成记忆树：为缺失 memory_tree 的题目调 LLM 生成层级大纲并落库。

一次调用处理一批题（batch prompting，默认 10 题），摊薄指令前缀、减少调用次数；
单题校验失败仅跳过该题（下次运行重试）；可随时 Ctrl+C 中断，已入库的不丢。

运行方式（在 backend/ 目录下）：
    .venv/Scripts/python scripts/build_memory_trees.py                      # 全部缺树的题
    .venv/Scripts/python scripts/build_memory_trees.py --stack agent        # 只跑 Agent 栈
    .venv/Scripts/python scripts/build_memory_trees.py --stack agent --limit 1   # 试点一题
"""
import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本能直接 import backend/ 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session as DBSession, select

from database import engine, init_db
from models import Question
from agents.memtree import generate_memory_trees_batch
from llm.errors import LLMError


def main() -> None:
    parser = argparse.ArgumentParser(description="批量生成记忆树")
    parser.add_argument("--stack", default=None, help="只处理该技术栈（如 agent）")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少题")
    parser.add_argument("--batch-size", type=int, default=10, help="每次 LLM 调用处理的题数")
    args = parser.parse_args()

    init_db()  # 确保迁移已应用（memory_tree 列存在）
    with DBSession(engine) as db:
        stmt = select(Question).where(Question.memory_tree.is_(None)).order_by(Question.id)
        if args.stack:
            stmt = stmt.where(Question.tech_stack == args.stack)
        questions = list(db.exec(stmt).all())
        if args.limit:
            questions = questions[: args.limit]

    if not questions:
        print("没有缺记忆树的题。")
        return
    print(f"待生成 {len(questions)} 题（批大小 {args.batch_size}）")

    done = failed = 0
    for i in range(0, len(questions), args.batch_size):
        batch = questions[i : i + args.batch_size]
        items = [{"id": q.id, "stem": q.stem, "answer": q.answer} for q in batch]
        try:
            trees = asyncio.run(generate_memory_trees_batch(items))
        except LLMError as exc:
            print(f"批次 {i // args.batch_size + 1} 失败（{exc}），跳过 {len(batch)} 题")
            failed += len(batch)
            continue
        with DBSession(engine) as db:
            for q in batch:
                tree = trees.get(q.id)
                if tree is None:
                    failed += 1
                    print(f"  题 #{q.id} 生成失败，跳过：{q.stem[:30]}")
                    continue
                db.get(Question, q.id).memory_tree = tree
                done += 1
                print(f"  题 #{q.id} 完成：{tree['title']}（{len(tree['children'])} 个一级要点）")
            db.commit()

    print(f"结束：成功 {done}，失败 {failed}。")


if __name__ == "__main__":
    main()
