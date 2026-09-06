# -*- coding: utf-8 -*-
"""单词查询接口：ECDICT 离线词典（data/ecdict.db，MIT 许可，76 万词条）。

查询顺序：自建补充表 supplement（题库里的框架名/术语/Python 标识符，
以及 ECDICT 释义在技术语境下误导的覆盖词，scripts/build_word_supplement.py
生成）→ ECDICT 精确匹配（大小写不敏感）→ 简单词形还原（复数/时态/比较级）
后对两张表各查一遍。找不到返回 {"found": false}，由前端提示"词典未收录"。
"""
import sqlite3

from fastapi import APIRouter

from config import PROJECT_ROOT

router = APIRouter()

DB_PATH = PROJECT_ROOT / "data" / "ecdict.db"
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    return _conn


def _lookup(word: str):
    return _db().execute(
        "SELECT word, phonetic, translation, exchange FROM words WHERE word = ? COLLATE NOCASE LIMIT 1",
        (word,),
    ).fetchone()


def _lookup_supplement(word: str):
    return _db().execute(
        "SELECT word, phonetic, translation, '' FROM supplement WHERE word = ? COLLATE NOCASE LIMIT 1",
        (word,),
    ).fetchone()


def _candidates(word: str):
    """简单词形还原候选：撇号 / 复数 / 时态 / 比较级，含双写辅音还原（running -> run）。"""
    w = word.strip().lower()
    seen = {w}
    yield w
    for suffix, repl in (
        ("'s", ""), ("ies", "y"), ("es", ""), ("s", ""),
        ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"),
        ("er", ""), ("est", ""),
    ):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            stem = w[: -len(suffix)] + repl
            for cand in (stem, stem[:-1] if len(stem) >= 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou" else ""):
                if cand and cand not in seen:
                    seen.add(cand)
                    yield cand


@router.get("/words/{word}")
def word_lookup(word: str) -> dict:
    """点击查词：返回音标 + 中文释义；命中的词与查询词不同时带上词形（如 went -> go）。"""
    for cand in _candidates(word):
        row = _lookup_supplement(cand) or _lookup(cand)
        if row:
            w, phonetic, translation, _exchange = row
            # ECDICT 变形词条（如 went）的音标列有时就是单词本身，没有意义
            if phonetic and phonetic.strip("'\"").lower() == w.lower():
                phonetic = ""
            return {
                "found": True,
                "query": word,
                "word": w,
                "phonetic": phonetic or "",
                "translation": translation or "",
            }
    return {"found": False, "query": word}
