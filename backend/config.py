# -*- coding: utf-8 -*-
"""全局配置：从项目根目录的 .env 读取环境变量。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用配置项，均可用环境变量覆盖。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Provider API Keys（未配置则该 Provider 视为不可用）
    deepseek_api_key: str = ""
    kimi_api_key: str = ""
    zhipu_api_key: str = ""
    doubao_api_key: str = ""

    # Provider 优先级，逗号分隔，按顺序尝试
    llm_provider_priority: str = "deepseek,kimi"

    # 模型名覆盖：仅对优先级第一的默认 Provider 生效；为空则用各 Provider 的默认模型
    #（设置面板可改，写入 .env 的 LLM_MODEL）
    llm_model: str = ""

    # 数据库文件路径（默认放在项目根目录 data/ 下）
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'bagu.db'}"

    # LLM 请求超时时间（秒）
    llm_timeout: float = 60.0

    @property
    def provider_priority(self) -> list[str]:
        """解析 LLM_PROVIDER_PRIORITY 为 provider 名称列表。"""
        return [p.strip().lower() for p in self.llm_provider_priority.split(",") if p.strip()]


settings = Settings()
