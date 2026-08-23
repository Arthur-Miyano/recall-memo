# -*- coding: utf-8 -*-
"""数据库校验器与合并器（修复方案 §9.1，从 api/datamove.py 拆出）。

- validate_source_db：合并前对源库做完整校验（§5.2 第 1~7 条），任一不通过抛 INVALID_DATABASE；
- merge_all：读源库各表 → 单事务幂等合并进当前库，任何异常整体回滚。

各表判重键（业务唯一键）：
- questions       题干与现有题 stem_similarity >= 0.85 视为重复（复用 importer 的判重口径）
- sessions        (mode, tech_stack, created_at) 完全相等
- records         (映射后 question_id, created_at, user_answer 全文)
- question_focus  映射后 question_id 已存在即跳过
- retry_queue     映射后 question_id 已存在即跳过
- question_groups (name, 映射后 question_ids 序列) 完全相等
- daily_stats     date 已存在则不插行，数值字段取 max（不能相加，相加会双倍计数）
- chat_sessions   (title, created_at) 完全相等
- chat_messages   (映射后 session_id, role, created_at, content 前 50 字)
- notes           (title, created_at) 完全相等
- llm_usage       (provider, model, created_at, total_tokens)

旧库缺某张表（更老版本表不全）→ 该表记 0/0 跳过，不报错；
旧库缺某列（如 annotated_answer 等后补列）→ 该列用模型默认值。
"""
import json
import logging
import sqlite3
from datetime import date as date_type
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session as DBSession, select

import database
from agents.importer import SIMILARITY_THRESHOLD, _norm_text, stem_similarity
from application.uploads import UploadRejectedError
from config import settings
from domain.session_state import VALID_SESSION_MODES, VALID_SESSION_STATES
from models import (
    ChatMessage, ChatSession, DailyStat, LLMUsage, Note,
    Question, QuestionFocus, QuestionGroup, Record, RetryQueueItem, Session,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """模型时间默认值口径与 models 各表的 _utcnow 保持一致（UTC）。"""
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# 类型归一：源库读出的字符串 → 模型字段类型
# ----------------------------------------------------------------------

def _dt(v) -> Optional[datetime]:
    """源库读出的时间字符串 → datetime（SQLite DATETIME 存为 ISO 字符串，统一转回 naive）。"""
    if v is None or isinstance(v, datetime):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _date(v) -> Optional[date_type]:
    if isinstance(v, date_type):
        return v
    try:
        return date_type.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return None


def _json_list(v) -> list:
    """JSON 列从源库读出是字符串，转回 list；异常/空值兜底空列表。"""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _json_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _zero() -> dict:
    return {"imported": 0, "skipped": 0}


# ----------------------------------------------------------------------
# 各表合并（db 为单事务 Session，全部完成后由 merge_all 统一 commit）
# ----------------------------------------------------------------------

def _merge_questions(db: DBSession, rows: Optional[list]) -> dict:
    """判重：与现有题（含本次新插入的）题干相似度 >= 0.85 即跳过，并记录 旧id→现有id。"""
    if rows is None:
        return _zero()
    result = _zero()
    # 预存现有题的归一化题干长度，先做长度剪枝再算相似度（大题库下避免 O(n²) 全量比对拖慢导入）
    existing = db.exec(select(Question)).all()
    pool = [(q, len(_norm_text(q.stem))) for q in existing]
    id_map: dict[int, int] = {}
    for row in rows:
        old_id = row.get("id")
        stem = row.get("stem") or ""
        stem_len = len(_norm_text(stem))
        dup = None
        if stem:
            for q, qlen in pool:
                # 相似度上界：两串长度差超过 ~1.4 倍时，ratio 与 bigram Jaccard 都不可能到 0.85
                if stem_len and qlen and max(stem_len, qlen) > 1.4 * min(stem_len, qlen):
                    continue
                if stem_similarity(stem, q.stem) >= SIMILARITY_THRESHOLD:
                    dup = q
                    break
        if dup is not None:
            result["skipped"] += 1
            if old_id is not None:
                id_map[old_id] = dup.id
            continue
        q = Question(
            stem=stem,
            answer=row.get("answer") or "",
            tech_stack=row.get("tech_stack") or "other",
            difficulty=row.get("difficulty") or "medium",
            keywords=_json_list(row.get("keywords")),
            tags=_json_list(row.get("tags")),
            variants=_json_list(row.get("variants")),
            created_at=_dt(row.get("created_at")) or _now(),
        )
        db.add(q)
        db.flush()  # 拿新 id（不提交，仍在单事务内）
        pool.append((q, stem_len))
        if old_id is not None:
            id_map[old_id] = q.id
        result["imported"] += 1
    result["id_map"] = id_map
    return result


def _merge_sessions(db: DBSession, rows: Optional[list], qmap: dict) -> dict:
    """判重键 (mode, tech_stack, created_at)；内部题目引用（question_ids/quiz_order/current）走题目映射。"""
    if rows is None:
        return _zero()
    result = _zero()
    keys = {(s.mode, s.tech_stack, s.created_at) for s in db.exec(select(Session)).all()}
    id_map: dict[int, int] = {}
    for row in rows:
        created = _dt(row.get("created_at"))
        key = (row.get("mode") or "", row.get("tech_stack") or "", created)
        if key in keys:
            result["skipped"] += 1
            continue
        remap = [qmap[i] for i in _json_list(row.get("question_ids")) if i in qmap]
        s = Session(
            mode=key[0],
            state=row.get("state") or "IDLE",
            current_question_id=qmap.get(row.get("current_question_id")),
            tech_stack=key[1],
            active_agent=row.get("active_agent") or "",
            question_ids=remap,
            quiz_order=[qmap[i] for i in _json_list(row.get("quiz_order")) if i in qmap],
            current_index=row.get("current_index") or 0,
            context=_json_dict(row.get("context")),
            created_at=created or _now(),
            updated_at=_dt(row.get("updated_at")) or created or _now(),
        )
        db.add(s)
        db.flush()
        keys.add(key)
        if row.get("id") is not None:
            id_map[row["id"]] = s.id
        result["imported"] += 1
    result["id_map"] = id_map
    return result


def _merge_records(db: DBSession, rows: Optional[list], qmap: dict, smap: dict) -> dict:
    """判重键 (映射后 question_id, created_at, user_answer 全文)。

    session_id / question_id 走映射；映射不上（旧库里引用了不存在的会话/题）的记录跳过。
    retry_of 指向的旧记录 id 在全部插入完毕后统一回填为新 id。
    """
    if rows is None:
        return _zero()
    result = _zero()
    keys = {(r.question_id, r.created_at, r.user_answer) for r in db.exec(select(Record)).all()}
    id_map: dict[int, int] = {}
    pending_retry: list[tuple[Record, int]] = []
    for row in rows:
        qid = qmap.get(row.get("question_id"))
        sid = smap.get(row.get("session_id"))
        if qid is None or sid is None:
            result["skipped"] += 1
            continue
        created = _dt(row.get("created_at"))
        key = (qid, created, row.get("user_answer") or "")
        if key in keys:
            result["skipped"] += 1
            continue
        rec = Record(
            session_id=sid,
            question_id=qid,
            user_answer=key[2],
            score_accuracy=row.get("score_accuracy"),
            score_logic=row.get("score_logic"),
            score_naturalness=row.get("score_naturalness"),
            score_total=row.get("score_total"),
            is_reciting=bool(row.get("is_reciting")) if row.get("is_reciting") is not None else None,
            annotated_answer=row.get("annotated_answer"),
            need_followup=bool(row.get("need_followup") or False),
            skipped=bool(row.get("skipped") or False),
            is_retry=bool(row.get("is_retry") or False),
            created_at=created or _now(),
        )
        db.add(rec)
        db.flush()
        keys.add(key)
        if row.get("id") is not None:
            id_map[row["id"]] = rec.id
        if row.get("retry_of"):
            pending_retry.append((rec, row["retry_of"]))
        result["imported"] += 1
    for rec, old_retry_of in pending_retry:
        if old_retry_of in id_map:
            rec.retry_of = id_map[old_retry_of]
    return result


def _merge_question_focus(db: DBSession, rows: Optional[list], qmap: dict) -> dict:
    """按映射后 question_id 集合并集：已存在（或题目未导入）即跳过。"""
    if rows is None:
        return _zero()
    result = _zero()
    have = {f.question_id for f in db.exec(select(QuestionFocus)).all()}
    for row in rows:
        qid = qmap.get(row.get("question_id"))
        if qid is None or qid in have:
            result["skipped"] += 1
            continue
        db.add(QuestionFocus(question_id=qid, created_at=_dt(row.get("created_at")) or _now()))
        have.add(qid)
        result["imported"] += 1
    return result


def _merge_retry_queue(db: DBSession, rows: Optional[list], qmap: dict) -> dict:
    """同 question_focus：按映射后 question_id 集合并集。"""
    if rows is None:
        return _zero()
    result = _zero()
    have = {i.question_id for i in db.exec(select(RetryQueueItem)).all()}
    for row in rows:
        qid = qmap.get(row.get("question_id"))
        if qid is None or qid in have:
            result["skipped"] += 1
            continue
        db.add(RetryQueueItem(
            question_id=qid,
            source=row.get("source") or "",
            created_at=_dt(row.get("created_at")) or _now(),
        ))
        have.add(qid)
        result["imported"] += 1
    return result


def _merge_question_groups(db: DBSession, rows: Optional[list], qmap: dict) -> dict:
    """判重键 (name, 映射后 question_ids 序列)；映射后为空的组跳过。"""
    if rows is None:
        return _zero()
    result = _zero()
    keys = {(g.name, tuple(g.question_ids)) for g in db.exec(select(QuestionGroup)).all()}
    for row in rows:
        mapped = [qmap[i] for i in _json_list(row.get("question_ids")) if i in qmap]
        if not mapped:
            result["skipped"] += 1
            continue
        key = (row.get("name") or "", tuple(mapped))
        if key in keys:
            result["skipped"] += 1
            continue
        db.add(QuestionGroup(
            name=key[0],
            question_ids=mapped,
            created_at=_dt(row.get("created_at")) or _now(),
        ))
        keys.add(key)
        result["imported"] += 1
    return result


def _merge_daily_stats(db: DBSession, rows: Optional[list]) -> dict:
    """按 date 合并：新日期直接插入；已有日期不插行（记 skipped），数值字段取 max 保证幂等。"""
    if rows is None:
        return _zero()
    result = _zero()
    have = {s.date: s for s in db.exec(select(DailyStat)).all()}
    for row in rows:
        d = _date(row.get("date"))
        if d is None:
            result["skipped"] += 1
            continue
        if d in have:
            cur = have[d]
            cur.total_count = max(cur.total_count, row.get("total_count") or 0)
            cur.success_count = max(cur.success_count, row.get("success_count") or 0)
            cur.fail_count = max(cur.fail_count, row.get("fail_count") or 0)
            db.add(cur)
            result["skipped"] += 1
            continue
        stat = DailyStat(
            date=d,
            total_count=row.get("total_count") or 0,
            success_count=row.get("success_count") or 0,
            fail_count=row.get("fail_count") or 0,
        )
        db.add(stat)
        have[d] = stat
        result["imported"] += 1
    return result


def _merge_chat_sessions(db: DBSession, rows: Optional[list]) -> dict:
    """判重键 (title, created_at)。"""
    if rows is None:
        return _zero()
    result = _zero()
    keys = {(s.title, s.created_at) for s in db.exec(select(ChatSession)).all()}
    id_map: dict[int, int] = {}
    for row in rows:
        created = _dt(row.get("created_at"))
        key = (row.get("title") or "新对话", created)
        if key in keys:
            result["skipped"] += 1
            continue
        s = ChatSession(
            title=key[0],
            created_at=created or _now(),
            updated_at=_dt(row.get("updated_at")) or created or _now(),
        )
        db.add(s)
        db.flush()
        keys.add(key)
        if row.get("id") is not None:
            id_map[row["id"]] = s.id
        result["imported"] += 1
    result["id_map"] = id_map
    return result


def _merge_chat_messages(db: DBSession, rows: Optional[list], cmap: dict) -> dict:
    """判重键 (映射后 session_id, role, created_at, content 前 50 字)；会话映射不上的消息跳过。"""
    if rows is None:
        return _zero()
    result = _zero()
    keys = {(m.session_id, m.role, m.created_at, m.content[:50]) for m in db.exec(select(ChatMessage)).all()}
    for row in rows:
        sid = cmap.get(row.get("session_id")) if row.get("session_id") is not None else None
        if row.get("session_id") is not None and sid is None:
            result["skipped"] += 1
            continue
        created = _dt(row.get("created_at"))
        content = row.get("content") or ""
        key = (sid, row.get("role") or "", created, content[:50])
        if key in keys:
            result["skipped"] += 1
            continue
        db.add(ChatMessage(
            session_id=sid,
            role=key[1],
            content=content,
            thinking=row.get("thinking"),
            created_at=created or _now(),
        ))
        keys.add(key)
        result["imported"] += 1
    return result


def _merge_notes(db: DBSession, rows: Optional[list]) -> dict:
    """判重键 (title, created_at)：同一时刻创建的同名笔记视为同一篇。"""
    if rows is None:
        return _zero()
    result = _zero()
    keys = {(n.title, n.created_at) for n in db.exec(select(Note)).all()}
    for row in rows:
        created = _dt(row.get("created_at"))
        key = (row.get("title") or "未命名笔记", created)
        if key in keys:
            result["skipped"] += 1
            continue
        db.add(Note(
            title=key[0],
            content=row.get("content") or "",
            created_at=created or _now(),
            updated_at=_dt(row.get("updated_at")) or created or _now(),
        ))
        keys.add(key)
        result["imported"] += 1
    return result


def _merge_llm_usage(db: DBSession, rows: Optional[list]) -> dict:
    """判重键 (provider, model, created_at, total_tokens)：同次调用的账单视为同一条。"""
    if rows is None:
        return _zero()
    result = _zero()
    keys = {(u.provider, u.model, u.created_at, u.total_tokens) for u in db.exec(select(LLMUsage)).all()}
    for row in rows:
        created = _dt(row.get("created_at"))
        key = (row.get("provider") or "", row.get("model") or "", created, row.get("total_tokens") or 0)
        if key in keys:
            result["skipped"] += 1
            continue
        db.add(LLMUsage(
            provider=key[0],
            model=key[1],
            prompt_tokens=row.get("prompt_tokens") or 0,
            completion_tokens=row.get("completion_tokens") or 0,
            total_tokens=key[3],
            cache_hit_tokens=row.get("cache_hit_tokens") or 0,
            cache_miss_tokens=row.get("cache_miss_tokens") or 0,
            status=row.get("status") or "ok",
            estimated=bool(row.get("estimated") or False),
            created_at=created or _now(),
        ))
        keys.add(key)
        result["imported"] += 1
    return result


# ----------------------------------------------------------------------
# 合并主流程
# ----------------------------------------------------------------------

def merge_all(src_path: Path) -> dict:
    """读源库各表 → 单事务合并进当前库。任何异常回滚后向上抛。"""
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        def read(table: str) -> Optional[list]:
            """整表读为 dict 列表；源库没有这张表（老版本）返回 None → 该表跳过不报错。"""
            if table not in tables:
                return None
            cur = src.execute(f'SELECT * FROM "{table}"')
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

        db = DBSession(database.engine)
        try:
            summary: dict = {}
            q = _merge_questions(db, read("questions"))
            summary["questions"] = {k: v for k, v in q.items() if k != "id_map"}
            s = _merge_sessions(db, read("sessions"), q.get("id_map", {}))
            summary["sessions"] = {k: v for k, v in s.items() if k != "id_map"}
            summary["records"] = _merge_records(db, read("records"), q.get("id_map", {}), s.get("id_map", {}))
            summary["question_focus"] = _merge_question_focus(db, read("question_focus"), q.get("id_map", {}))
            summary["retry_queue"] = _merge_retry_queue(db, read("retry_queue"), q.get("id_map", {}))
            summary["question_groups"] = _merge_question_groups(db, read("question_groups"), q.get("id_map", {}))
            summary["daily_stats"] = _merge_daily_stats(db, read("daily_stats"))
            c = _merge_chat_sessions(db, read("chat_sessions"))
            summary["chat_sessions"] = {k: v for k, v in c.items() if k != "id_map"}
            summary["chat_messages"] = _merge_chat_messages(db, read("chat_messages"), c.get("id_map", {}))
            summary["notes"] = _merge_notes(db, read("notes"))
            summary["llm_usage"] = _merge_llm_usage(db, read("llm_usage"))
            db.commit()
            return summary
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    finally:
        src.close()


# ----------------------------------------------------------------------
# 源库校验（修复方案 §5.2）：完整性 / schema / 数据约束全部通过后才备份并合并
# ----------------------------------------------------------------------

# 允许出现的表 → 必需列（缺必需列拒绝；缺后补列沿用"该列用模型默认值"的合并口径）
_ALLOWED_TABLES: dict[str, set[str]] = {
    "questions": {"id", "stem"},
    "sessions": {"id"},
    "records": {"id", "question_id", "session_id"},
    "question_focus": {"question_id"},
    "retry_queue": {"question_id"},
    "question_groups": {"id", "name"},
    "daily_stats": {"date"},
    "chat_sessions": {"id"},
    "chat_messages": {"session_id", "role", "content"},
    "notes": {"id", "title"},
    "llm_usage": {"id"},
    "workflow_operations": {"id"},
    # 操作日志：与 workflow_operations 同为允许但不合并的表（审计记录属于各环境自身，不随迁移搬运）
    "operation_logs": {"id", "action"},
}
_SYSTEM_TABLES = {"sqlite_sequence"}

# 长文本/JSON 字段长度上限检查（列存在才查）
_LONG_TEXT_COLUMNS: dict[str, tuple] = {
    "questions": ("stem", "answer"),
    "records": ("user_answer", "annotated_answer"),
    "sessions": ("context",),
    "chat_messages": ("content", "thinking"),
    "notes": ("content",),
}

# JSON 列 → 期望顶层类型（列存在且值非 NULL 才校验）
_JSON_COLUMNS: dict[str, tuple] = {
    "questions": (("keywords", list), ("tags", list), ("variants", list)),
    "sessions": (("question_ids", list), ("quiz_order", list), ("context", dict)),
    "question_groups": (("question_ids", list),),
    "chat_messages": (("thinking", list),),
}

# 外键引用（含自引用 retry_of）：(表, 外键列, 被引用表, 被引用列)
_FK_CHECKS = (
    ("records", "question_id", "questions", "id"),
    ("records", "session_id", "sessions", "id"),
    ("records", "retry_of", "records", "id"),
    ("question_focus", "question_id", "questions", "id"),
    ("retry_queue", "question_id", "questions", "id"),
    ("chat_messages", "session_id", "chat_sessions", "id"),
    ("sessions", "current_question_id", "questions", "id"),
)

# JSON 内嵌的题目 id 引用（question_groups.question_ids / sessions.question_ids/quiz_order）
_JSON_ID_REFS = (
    ("question_groups", "question_ids"),
    ("sessions", "question_ids"),
    ("sessions", "quiz_order"),
)


def _invalid_db(reason: str) -> UploadRejectedError:
    """数据库校验失败的统一出口：稳定 INVALID_DATABASE，细节只进日志（§4.2 脱敏口径）。"""
    logger.warning("数据库合并导入校验未通过：%s", reason)
    return UploadRejectedError("INVALID_DATABASE", f"数据库文件校验未通过（{reason}）")


def _validate_values(src: sqlite3.Connection, tables: set[str], cols: dict[str, set[str]]) -> None:
    """值域与外键的确定性校验（§5.2 第 7 条）：JSON 合法、mode/state/分数/日期合法、无悬空引用。"""
    def has_col(table: str, column: str) -> bool:
        return table in tables and column in cols.get(table, set())

    # JSON 列：可解析且顶层类型匹配
    for table, columns in _JSON_COLUMNS.items():
        for col_name, expected in columns:
            if not has_col(table, col_name):
                continue
            rows = src.execute(f'SELECT "{col_name}" FROM "{table}" WHERE "{col_name}" IS NOT NULL')
            for (raw,) in rows:
                try:
                    parsed = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    raise _invalid_db(f"{table}.{col_name} 含非法 JSON")
                if not isinstance(parsed, expected):
                    raise _invalid_db(f"{table}.{col_name} 的 JSON 类型不符")

    # sessions：mode / state 合法值（引用 domain.session_state 集中定义，§6.1）
    if has_col("sessions", "mode"):
        placeholders = ",".join("?" for _ in VALID_SESSION_MODES)
        bad = src.execute(
            f"SELECT COUNT(*) FROM sessions WHERE mode NOT IN ({placeholders})", VALID_SESSION_MODES
        ).fetchone()[0]
        if bad:
            raise _invalid_db("存在非法的会话 mode 值")
    if has_col("sessions", "state"):
        placeholders = ",".join("?" for _ in VALID_SESSION_STATES)
        bad = src.execute(
            f"SELECT COUNT(*) FROM sessions WHERE state NOT IN ({placeholders})", VALID_SESSION_STATES
        ).fetchone()[0]
        if bad:
            raise _invalid_db("存在非法的会话 state 值")

    # records：分数必须为 NULL 或 0~100
    for col_name in ("score_accuracy", "score_logic", "score_naturalness", "score_total"):
        if has_col("records", col_name):
            bad = src.execute(
                f'SELECT COUNT(*) FROM records WHERE "{col_name}" IS NOT NULL '
                f'AND ("{col_name}" < 0 OR "{col_name}" > 100)'
            ).fetchone()[0]
            if bad:
                raise _invalid_db("存在超出 0~100 范围的分数")

    # daily_stats：date 必须可解析为 ISO 日期
    if has_col("daily_stats", "date"):
        for (raw,) in src.execute("SELECT date FROM daily_stats"):
            if _date(raw) is None:
                raise _invalid_db("daily_stats 含非法日期")

    # 外键引用（含自引用）
    for table, fk, ref_table, ref_col in _FK_CHECKS:
        if has_col(table, fk) and has_col(ref_table, ref_col):
            bad = src.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{fk}" IS NOT NULL AND '
                f'"{fk}" NOT IN (SELECT "{ref_col}" FROM "{ref_table}")'
            ).fetchone()[0]
            if bad:
                raise _invalid_db(f"{table}.{fk} 存在悬空引用")

    # JSON 内嵌的题目 id 引用必须指向源库中存在的题
    if "questions" in tables:
        qids = {r[0] for r in src.execute("SELECT id FROM questions")}
        for table, col_name in _JSON_ID_REFS:
            if not has_col(table, col_name):
                continue
            for (raw,) in src.execute(
                f'SELECT "{col_name}" FROM "{table}" WHERE "{col_name}" IS NOT NULL'
            ):
                ids = json.loads(raw)  # JSON 合法性已在上面校验过
                if any(not isinstance(i, int) or isinstance(i, bool) or i not in qids for i in ids):
                    raise _invalid_db(f"{table}.{col_name} 存在悬空的题目引用")


def validate_source_db(src_path: Path) -> None:
    """合并前对源库做完整校验（§5.2 第 1~7 条）：任一不通过抛 INVALID_DATABASE，不备份不合并。

    大小与 SQLite magic 已在上传策略层校验（uploads.validate_db_upload）。
    """
    try:
        src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    except sqlite3.Error:
        raise _invalid_db("文件无法作为 SQLite 数据库打开") from None
    try:
        # 2. 完整性快速检查（损坏的页/索引在此暴露）
        try:
            row = src.execute("PRAGMA quick_check").fetchone()
        except sqlite3.Error:
            raise _invalid_db("数据库文件已损坏") from None
        if not row or row[0] != "ok":
            raise _invalid_db("数据库完整性检查未通过")
        # 3. schema_version：读取留痕（每次 schema 变更自增，0 表示空库）
        schema_version = src.execute("PRAGMA schema_version").fetchone()[0]
        logger.info("源库 quick_check 通过，schema_version=%s", schema_version)
        # 4/5. schema 检查：未知表、trigger、view、虚拟表一律拒绝
        objects = src.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
        for obj_type, name, sql in objects:
            if obj_type == "table":
                if name not in _ALLOWED_TABLES and name not in _SYSTEM_TABLES:
                    raise _invalid_db("包含未知表，不是本工具导出的数据库")
            elif obj_type in ("trigger", "view"):
                raise _invalid_db("包含触发器或视图，拒绝导入")
            if sql and "CREATE VIRTUAL TABLE" in str(sql).upper():
                raise _invalid_db("包含虚拟表，拒绝导入")
        tables = {name for t, name, _ in objects if t == "table"} - _SYSTEM_TABLES
        cols = {t: {r[1] for r in src.execute(f'PRAGMA table_info("{t}")')} for t in tables}
        for table in tables:
            if _ALLOWED_TABLES[table] - cols[table]:
                raise _invalid_db("缺少必需列，schema 版本不兼容")
        # 6. 每张表行数与长文本/JSON 字段长度上限
        for table in tables:
            count = src.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if count > settings.db_import_max_rows:
                raise _invalid_db(f"单表数据量超过上限（{settings.db_import_max_rows} 行）")
            for col_name in _LONG_TEXT_COLUMNS.get(table, ()):
                if col_name in cols[table]:
                    longest = src.execute(
                        f'SELECT MAX(LENGTH("{col_name}")) FROM "{table}"'
                    ).fetchone()[0]
                    if longest and longest > settings.db_import_max_field_chars:
                        raise _invalid_db("存在超过上限的长文本字段")
        # 7. 值域与外键的确定性校验
        _validate_values(src, tables, cols)
    finally:
        src.close()
