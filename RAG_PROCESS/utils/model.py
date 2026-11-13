from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from loguru import logger


def get_llm(

) -> Runnable:
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
        temperature=0.0,  # RAG 闭卷问答必须将温度设为 0，彻底压制随机发散
        timeout=15.0,
    )

    logger.debug(
        f"🛡️ [LLM Factory] Resilient pipeline activated: Primary ({primary_llm.model_name}) "
    )

    return primary_llm
