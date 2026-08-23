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

    # ------------------------------------------------------------------
    # 上传与导入资源上限（修复方案 §5.1，环境变量可覆盖）
    # ------------------------------------------------------------------
    # 单文件最大字节数（默认 20 MiB）
    upload_max_file_bytes: int = 20 * 1024 * 1024
    # 单批最多文件数
    upload_max_files: int = 10
    # 单次总上传最大字节数（默认 50 MiB）
    upload_max_total_bytes: int = 50 * 1024 * 1024
    # PDF 最多页数
    pdf_max_pages: int = 300
    # 提取文本最大字符数（粘贴文本与文件解码文本同口径）
    extract_max_chars: int = 2_000_000
    # 单任务最大题目数（规整后截断，同时限制 LLM 补全规模）
    import_max_questions: int = 2000
    # 单任务 LLM 请求数上限
    import_max_llm_calls: int = 200
    # 单任务 Token 预算（按输入字符数估算：中文约 1 字 ≈ 1 token，偏保守方向）
    import_max_token_budget: int = 2_000_000
    # 单任务总运行时间上限（秒）
    import_max_seconds: float = 600.0
    # 数据库合并导入：每张表最大行数
    db_import_max_rows: int = 200_000
    # 数据库合并导入：单个文本/JSON 字段最大字符数
    db_import_max_field_chars: int = 1_000_000

    @property
    def provider_priority(self) -> list[str]:
        """解析 LLM_PROVIDER_PRIORITY 为 provider 名称列表。"""
        return [p.strip().lower() for p in self.llm_provider_priority.split(",") if p.strip()]


settings = Settings()
