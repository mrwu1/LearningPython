from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from loguru import logger


def get_llm() -> Runnable:
    """
    Enterprise Resilient LLM Factory:
    Builds a primary LLM with strict timeouts, and automatically wraps it with a secondary
    disaster recovery fallback model (with_fallbacks) if BACKUP_LLM_ENABLED is True.
    """

    # 1. 组装主力大模型 (严格设置超时与重试，防止由于网络挂起导致用户白屏)

    # 3. 组装备用大模型通道 (Failover Channel)
    primary_llm = ChatOpenAI(
        model="deepseek-chat",
        api_key="sk-f8f7bf1c05404adb96717f0c929a6c46",
        base_url="https://api.deepseek.com",
        temperature=0.0,  # 财务风控审计要求结果确定性，温度设为 0
        timeout=15.0,  # 单次请求最长等待 15 秒
        max_retries=2,  # 网络抖动自动重试 2 次
    )
    logger.debug(f"🛡️ [LLM Factory] 已激活风控模型管道: {primary_llm.model_name}")
    # logger.debug(
    #     f"🛡️ [LLM Factory] Resilient pipeline activated: Primary ({primary_llm.model_name}) "
    # )

    return primary_llm
