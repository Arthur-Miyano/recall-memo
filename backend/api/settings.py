# -*- coding: utf-8 -*-
"""模型与密钥设置接口。

安全红线：
- API Key 只允许写入项目根目录的 .env（已在 .gitignore），并同步到 os.environ / settings；
- 所有响应只回掩码（sk-••••81d7）与"是否已配置"，绝不出完整 Key；
- 本模块不记录任何含 Key 的日志，异常信息也不携带 Key。
"""
import os
import tempfile
import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import PROJECT_ROOT, settings
from llm import llm_router
from llm.router import PROVIDER_ENV_VAR, PROVIDER_KEY_ATTR, PROVIDER_REGISTRY

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_PATH = PROJECT_ROOT / ".env"


def _mask(key: str) -> Optional[str]:
    """Key 掩码：前 3 位 + •••• + 后 4 位；太短则全掩码。"""
    if not key:
        return None
    if len(key) <= 7:
        return "••••"
    return f"{key[:3]}••••{key[-4:]}"


# 同进程写锁（§10）：多线程并发保存设置时 .env 读写串行化
_ENV_LOCK = threading.Lock()


def _write_env(updates: dict[str, str]) -> None:
    """把 KEY=VALUE 写入项目根 .env：已存在的行原位替换，其余行原样保留。

    原子写入（§10）：先写同目录临时文件再 os.replace——崩溃/失败时 .env 要么旧要么新，
    绝不撕裂；临时文件失败即删，不留半截。同进程并发由 _ENV_LOCK 串行化。
    """
    with _ENV_LOCK:
        lines: list[str] = []
        if ENV_PATH.exists():
            lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        remaining = dict(updates)
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                name = stripped.split("=", 1)[0].strip()
                if name in remaining:
                    out.append(f"{name}={remaining.pop(name)}")
                    continue
            out.append(line)
        for name, value in remaining.items():
            out.append(f"{name}={value}")
        content = "\n".join(out) + "\n"
        fd, tmp_name = tempfile.mkstemp(dir=ENV_PATH.parent, prefix=".env.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            _replace(tmp_name, ENV_PATH)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def _replace(src: str, dst) -> None:
    """os.replace 的 Windows 兜底：杀软/索引器短暂占用目标时会偶发 PermissionError，短暂重试。"""
    for attempt in range(5):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01)


def _current_payload() -> dict:
    """GET 响应形状：provider / 模型名 / Key 掩码与配置状态 / 环境变量检测结果。"""
    priority = settings.provider_priority
    provider = priority[0] if priority else ""
    key = getattr(settings, PROVIDER_KEY_ATTR.get(provider, ""), "") if provider else ""
    client = llm_router.get_client(provider) if provider else None
    return {
        "providers": list(PROVIDER_REGISTRY.keys()),
        "provider": provider,
        "model": settings.llm_model or (client.model if client else ""),
        "key_configured": bool(key),
        "key_masked": _mask(key),
        # 「从环境变量提取」：只报告 os.environ 里是否检测到，同样只回掩码
        "env_detected": {
            name: {"env_var": PROVIDER_ENV_VAR[name], "masked": _mask(os.environ.get(PROVIDER_ENV_VAR[name], ""))}
            for name in PROVIDER_REGISTRY
        },
    }


@router.get("/llm")
def get_llm_settings():
    return _current_payload()


class LLMSettingsRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None  # 为空表示不修改 Key


@router.post("/llm")
def update_llm_settings(req: LLMSettingsRequest):
    provider = req.provider.strip().lower()
    if provider not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=400, detail=f"暂不支持的 Provider：{req.provider}（已接入：{', '.join(PROVIDER_REGISTRY)}）")

    env_updates: dict[str, str] = {}
    if req.api_key:
        env_var = PROVIDER_ENV_VAR[provider]
        env_updates[env_var] = req.api_key
    if req.model:
        env_updates["LLM_MODEL"] = req.model

    # 所选 Provider 提到优先级第一位
    rest = [p for p in settings.provider_priority if p != provider]
    priority = ",".join([provider, *rest])
    env_updates["LLM_PROVIDER_PRIORITY"] = priority

    # 先持久化；写盘失败时不改变当前进程配置。
    _write_env(env_updates)
    for name, value in env_updates.items():
        os.environ[name] = value
    if req.api_key:
        setattr(settings, PROVIDER_KEY_ATTR[provider], req.api_key)
    if req.model:
        settings.llm_model = req.model
    settings.llm_provider_priority = priority
    llm_router.reload()
    return _current_payload()
