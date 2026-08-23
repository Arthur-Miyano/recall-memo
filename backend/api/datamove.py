# -*- coding: utf-8 -*-
"""数据备份与一键迁移（HTTP 层）：整库导出 / 旧库合并导入。

- GET  /settings/export    —— 把当前 SQLite 库整个下载（导出前先 WAL checkpoint 保证落盘完整）。
- POST /settings/import-db —— 上传旧环境的 bagu.db，幂等合并进当前库。

本文件只保留参数转换与错误映射（§9.1）：
源库校验与合并逻辑在 application/dbmerge.py（validate_source_db / merge_all）。

合并安全红线：
1. 合并前把当前库复制为 data/bagu.db.bak-时间戳（出错可手工回滚文件）；
2. 全部合并在一个事务里完成，任何一步失败整体回滚，当前库不留半成品；
3. 幂等：同一份文件重复导入不会产生重复数据（各表判重键见 application/dbmerge.py docstring）。
"""
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text

import database
from application.dbmerge import merge_all, validate_source_db
from application.uploads import read_upload, validate_db_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# ----------------------------------------------------------------------
# 文件级工具（与当前库路径/备份相关，属 HTTP 层的环境适配）
# ----------------------------------------------------------------------

def _db_path() -> Path:
    """当前引擎对应的 SQLite 文件路径（测试里 engine 被替换为临时库，天然隔离）。"""
    return Path(database.engine.url.database)


def _checkpoint() -> None:
    """WAL checkpoint：把 -wal 里的数据写回主文件，保证文件级复制/下载是完整的。

    非 WAL 模式下该语句是无害空操作。
    """
    with database.engine.connect() as conn:
        conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))


def _backup_current() -> Optional[Path]:
    """合并前备份当前库到 同目录/bagu.db.bak-时间戳；库文件还不存在（全新环境）则返回 None。"""
    src = _db_path()
    if not src.exists():
        return None
    _checkpoint()
    dst = src.with_name(f"{src.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(src, dst)
    return dst


# ----------------------------------------------------------------------
# 路由
# ----------------------------------------------------------------------

@router.get("/export")
def export_db():
    """整库导出：WAL checkpoint 后直接下载 SQLite 文件。"""
    _checkpoint()
    path = _db_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="数据库文件不存在")
    filename = f"recall-backup-{datetime.now().strftime('%Y%m%d')}.db"
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@router.post("/import-db")
async def import_db(file: UploadFile = File(...)):
    """旧库合并导入：上传策略（§5.1 大小/签名）→ 源库完整校验（§5.2）→ 备份 → 单事务幂等合并。"""
    content = await read_upload(file)
    validate_db_upload(file.filename or "", content)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    try:
        tmp.write(content)
    finally:
        tmp.close()

    try:
        # 完整校验通过后才创建备份并开始合并（§5.2 第 8 条）
        validate_source_db(Path(tmp.name))
        backup = _backup_current()
        try:
            summary = merge_all(Path(tmp.name))
        except HTTPException:
            raise
        except Exception as exc:
            # 脱敏（§4.2）：备份绝对路径与原始异常只进服务端日志，响应只给稳定提示
            logger.exception("数据库合并导入失败（备份文件：%s）", backup)
            raise HTTPException(
                status_code=500,
                detail="合并失败，已整体回滚，当前数据未受影响；详细原因见服务端日志",
            ) from exc
        # 响应只回备份文件名，不回本地绝对路径
        return {"backup": backup.name if backup else None, "tables": summary}
    finally:
        os.unlink(tmp.name)  # 临时上传文件用完即删
