from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from loguru import logger

from app.core.config import settings


def get_llm(
        temperature: float = 0.0,
        streaming: bool = True,# 👈 默认开启流式 Token 回调
        timeout: float | None = None,
        max_retries: int | None = None
) -> Runnable:
    """
    Enterprise Resilient LLM Factory:
    Builds a primary LLM with strict timeouts, and automatically wraps it with a secondary
    disaster recovery fallback model (with_fallbacks) if BACKUP_LLM_ENABLED is True.
    """
    act_timeout = timeout or settings.PRIMARY_LLM_TIMEOUT
    act_retries = max_retries if max_retries is not None else settings.PRIMARY_LLM_MAX_RETRIES

    # 1. 组装主力大模型 (严格设置超时与重试，防止由于网络挂起导致用户白屏)
    primary_llm = ChatOpenAI(
        model=settings.DEEPSEEK_MODEL if hasattr(settings, "DEEPSEEK_MODEL") else "deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY.get_secret_value(),
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=temperature,
        streaming=streaming,
        timeout=act_timeout,
        max_retries=act_retries
    )

    # 2. 如果未配置备用通道，降级返回纯主力模型
    backup_key = settings.BACKUP_LLM_API_KEY.get_secret_value() if hasattr(settings.BACKUP_LLM_API_KEY,
                                                                           "get_secret_value") else str(
        settings.BACKUP_LLM_API_KEY)
    if not settings.BACKUP_LLM_ENABLED or not backup_key:
        return primary_llm

    # 3. 组装备用大模型通道 (Failover Channel)
    backup_llm = ChatOpenAI(
        model=settings.BACKUP_LLM_MODEL,
        api_key=backup_key,
        base_url=settings.BACKUP_LLM_BASE_URL,
        temperature=temperature,
        streaming=streaming,
        timeout=25.0,  # 备用通道给予更宽裕的超时
        max_retries=2
    )

    logger.debug(
        f"🛡️ [LLM Factory] Resilient pipeline activated: Primary ({primary_llm.model_name}) "
        f"-> Fallback ({backup_llm.model_name})"
    )

    # 4. 关键核心：绑定 Fallback，主力发生 500/503/429/Timeout 时自动无感切换！
    resilient_llm = primary_llm.with_fallbacks([backup_llm])
    return resilient_llm
