# -*- coding: utf-8 -*-
"""统一 LLM 异常类型（修复方案 §4.1）。

分类语义：
- LLMTimeoutError：超时，允许有限重试或切换 Provider；
- LLMRateLimitError：限流（429），退避后重试/切换；
- LLMTemporaryError：网络失败、Provider 5xx、响应结构无法识别，允许切换；
- LLMAuthenticationError：401/403/未配置 Key，不切换，提示检查配置；
- LLMRequestError：400/404/422（Prompt 过长、模型不存在、参数/Schema 错误），不切换；
- LLMOutputValidationError：输出无法解析或未通过约束，可进行一次受控重试。

所有异常消息均为脱敏后的简短描述（不含 URL、请求头、Prompt、Provider 原始响应），
可以直接进日志；原始异常通过 __cause__ 链保留给服务端日志（logging exc_info）。
"""


class LLMError(RuntimeError):
    """LLM 调用失败的统一基类。"""


class LLMTimeoutError(LLMError):
    """请求超时（含超出路由统一截止时间）。"""


class LLMRateLimitError(LLMError):
    """Provider 限流（HTTP 429）。"""


class LLMTemporaryError(LLMError):
    """临时故障：网络失败、Provider 5xx、响应结构无法识别。"""


class LLMAuthenticationError(LLMError):
    """认证失败（HTTP 401/403、未配置 API Key）：不切换，需检查配置。"""


class LLMRequestError(LLMError):
    """请求本身非法（HTTP 400/404/422）：模型不存在、Prompt 过长、参数/Schema 错误，不切换。"""


class LLMOutputValidationError(LLMError):
    """输出无法解析或未通过输出模型校验（受控重试一次后仍失败）。"""
