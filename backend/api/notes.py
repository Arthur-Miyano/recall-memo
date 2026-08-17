# -*- coding: utf-8 -*-
"""笔记接口：文档式笔记的 CRUD + 背诵划句片段追加。"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from api.deps import get_db
from models import Note

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreate(BaseModel):
    title: str = "未命名笔记"


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class AppendRequest(BaseModel):
    text: str          # 划句收藏的句子
    source: str = ""   # 来源（一般是题干），便于日后回溯


def _get_note(db: DBSession, note_id: int) -> Note:
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return note


def _brief(n: Note) -> dict:
    plain = (n.content or "").replace("\n", " ").strip()
    return {
        "id": n.id,
        "title": n.title,
        "excerpt": plain[:60],
        "updated_at": n.updated_at.isoformat(),
    }


def _full(n: Note) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "created_at": n.created_at.isoformat(),
        "updated_at": n.updated_at.isoformat(),
    }


@router.get("")
def list_notes(db: DBSession = Depends(get_db)):
    """笔记列表（按最近编辑倒序，只回摘要，不回全文）。"""
    notes = db.exec(select(Note).order_by(Note.updated_at.desc())).all()
    return {"count": len(notes), "items": [_brief(n) for n in notes]}


@router.post("")
def create_note(req: NoteCreate, db: DBSession = Depends(get_db)):
    note = Note(title=req.title.strip() or "未命名笔记")
    db.add(note)
    db.commit()
    db.refresh(note)
    return _full(note)


@router.get("/{note_id}")
def get_note(note_id: int, db: DBSession = Depends(get_db)):
    return _full(_get_note(db, note_id))


@router.put("/{note_id}")
def update_note(note_id: int, req: NoteUpdate, db: DBSession = Depends(get_db)):
    """编辑器自动保存：标题/正文按需更新，刷新 updated_at。"""
    note = _get_note(db, note_id)
    if req.title is not None:
        note.title = req.title.strip() or "未命名笔记"
    if req.content is not None:
        note.content = req.content
    note.updated_at = datetime.now(timezone.utc)
    db.add(note)
    db.commit()
    db.refresh(note)
    return _full(note)


@router.delete("/{note_id}")
def delete_note(note_id: int, db: DBSession = Depends(get_db)):
    note = _get_note(db, note_id)
    db.delete(note)
    db.commit()
    return {"ok": True}


@router.post("/{note_id}/append")
def append_snippet(note_id: int, req: AppendRequest, db: DBSession = Depends(get_db)):
    """背诵划句收藏：以引用块形式追加到笔记末尾。

    格式（纯文本约定，前端按 > 前缀渲染引用样式）：
        > 收藏的句子
        —— 来源题干
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="收藏内容为空")
    note = _get_note(db, note_id)
    block = f"> {text}"
    if req.source.strip():
        block += f"\n—— {req.source.strip()}"
    note.content = (note.content or "") + ("\n\n" if note.content else "") + block
    note.updated_at = datetime.now(timezone.utc)
    db.add(note)
    db.commit()
    db.refresh(note)
    return _full(note)
