# -*- coding: utf-8 -*-
"""存量数据检查（修复方案 §6.3）：约束启用前/迁移前检查非法数据。

用法（在 backend/ 目录下）：
    python scripts/check_data_integrity.py [db_path]     # 默认 ../data/bagu.db

退出码：0 = 数据干净；1 = 发现非法数据（逐项列出并给出可恢复提示）。
发现非法数据时应先修复再升级/迁移，不要强行继续。
"""
import sqlite3
import sys
from pathlib import Path

# 让脚本可直接以文件路径运行（python scripts/check_data_integrity.py）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.session_state import VALID_SESSION_MODES, VALID_SESSION_STATES  # noqa: E402

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "bagu.db"

# 外键孤儿检查：(表, 外键列, 被引用表, 被引用列)
_FK_CHECKS = (
    ("records", "session_id", "sessions", "id"),
    ("records", "question_id", "questions", "id"),
    ("records", "retry_of", "records", "id"),
    ("records", "operation_id", "workflow_operations", "id"),
    ("retry_queue", "question_id", "questions", "id"),
    ("question_focus", "question_id", "questions", "id"),
    ("chat_messages", "session_id", "chat_sessions", "id"),
    ("sessions", "current_question_id", "questions", "id"),
    ("workflow_operations", "session_id", "sessions", "id"),
    ("workflow_operations", "question_id", "questions", "id"),
)

# 唯一约束复查（约束只对新库生效，存量库需确认无重复）：(表, 列)
_UNIQUE_CHECKS = (
    ("retry_queue", "question_id"),
    ("question_focus", "question_id"),
    ("daily_stats", "date"),
    ("workflow_operations", "idempotency_key"),
    ("records", "operation_id"),
)

_SCORE_COLUMNS = ("score_accuracy", "score_logic", "score_naturalness", "score_total")


def check_database(db_path: Path) -> list[str]:
    """检查存量数据，返回违规描述列表（空列表 = 干净）。"""
    violations: list[str] = []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        def has(table: str, column: str) -> bool:
            if table not in tables:
                return False
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            return column in cols

        # 1. 外键孤儿记录
        for table, fk, ref_table, ref_col in _FK_CHECKS:
            if not (has(table, fk) and has(ref_table, ref_col)):
                continue
            rows = conn.execute(
                f'SELECT "{table}".rowid, "{fk}" FROM "{table}" WHERE "{fk}" IS NOT NULL AND '
                f'"{fk}" NOT IN (SELECT "{ref_col}" FROM "{ref_table}")'
            ).fetchall()
            for rowid, ref in rows:
                violations.append(f"{table} rowid={rowid}：{fk}={ref} 引用了不存在的 {ref_table}.{ref_col}")

        # 2. 唯一约束复查
        for table, column in _UNIQUE_CHECKS:
            if not has(table, column):
                continue
            rows = conn.execute(
                f'SELECT "{column}", COUNT(*) c FROM "{table}" WHERE "{column}" IS NOT NULL '
                f'GROUP BY "{column}" HAVING c > 1'
            ).fetchall()
            for value, count in rows:
                violations.append(f"{table}.{column}={value} 重复 {count} 次（应为唯一）")

        # 3. 分数范围（0~100 或 NULL）
        for col in _SCORE_COLUMNS:
            if not has("records", col):
                continue
            rows = conn.execute(
                f'SELECT id, "{col}" FROM records WHERE "{col}" IS NOT NULL AND ("{col}" < 0 OR "{col}" > 100)'
            ).fetchall()
            for rid, score in rows:
                violations.append(f"records id={rid}：{col}={score} 超出 0~100 范围")

        # 4. 会话 mode / state 合法值
        if has("sessions", "mode"):
            placeholders = ",".join("?" for _ in VALID_SESSION_MODES)
            for rid, mode in conn.execute(
                f"SELECT id, mode FROM sessions WHERE mode NOT IN ({placeholders})", VALID_SESSION_MODES
            ):
                violations.append(f"sessions id={rid}：mode={mode!r} 非法（应为 {'/'.join(VALID_SESSION_MODES)}）")
        if has("sessions", "state"):
            placeholders = ",".join("?" for _ in VALID_SESSION_STATES)
            for rid, state in conn.execute(
                f"SELECT id, state FROM sessions WHERE state NOT IN ({placeholders})", VALID_SESSION_STATES
            ):
                violations.append(f"sessions id={rid}：state={state!r} 非法")
    finally:
        conn.close()
    return violations


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    if not db_path.exists():
        print(f"数据库文件不存在：{db_path}")
        return 1
    violations = check_database(db_path)
    if not violations:
        print(f"[OK] {db_path} 数据检查通过，可以安全迁移/升级。")
        return 0
    print(f"[FAIL] {db_path} 发现 {len(violations)} 处非法数据，已停止，请先修复再迁移：")
    for v in violations:
        print(f"  - {v}")
    print(
        "\n可恢复提示：\n"
        "  1. 先用「设置 → 导出备份」或直接复制 data/bagu.db 保留一份快照；\n"
        "  2. 孤儿记录可删除（如 DELETE FROM <表> WHERE rowid=<rowid>），"
        "越界分数可置 NULL（未评分），非法 mode/state 可置回 IDLE/memorize；\n"
        "  3. 修复后重新运行本脚本确认通过，再启动服务执行迁移。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
