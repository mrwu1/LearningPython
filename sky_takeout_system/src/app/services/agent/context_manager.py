from typing import Sequence, Optional

from langchain_core.messages import BaseMessage, SystemMessage, trim_messages
from loguru import logger

from app.core.config import settings


def prepare_trimmed_messages(
        system_prompt:str,
        raw_messages:Sequence[BaseMessage],
        max_messages:Optional[int] = None,
        ## 建议给 max_messages 增加默认值 None，调用方不传时不会报 missing argument
)->list[BaseMessage]:
    limit = max_messages or settings.MAX_CONTEXT_MESSAGES

    # less than limit, return the origin
    if len(raw_messages) <= limit:
        return [SystemMessage(content=system_prompt)] + list(raw_messages)

    # trim the messages
    trimmed_dialogue = trim_messages(
        messages=raw_messages,
        max_tokens=limit,
        token_counter=len,  # 以消息条数为滑动单位
        strategy="last",  # 严格保留最近的会话
        start_on="human",  # 强制切片的第一条必须是用户的提问
        include_system=False,  # 排除系统提示词，稍后单独置顶
    )
    evicted_count = len(raw_messages) - len(trimmed_dialogue)
    logger.debug(
        f"✂️✂️✂️ [Context Optimizer] Trimmed raw messages from {len(raw_messages)} down to "
        f"{len(trimmed_dialogue)} recent turns (Evicted {evicted_count} historical messages; "
        f"Saved ~{evicted_count * 120} prompt tokens)."
    )
    # 3. 将权威系统提示词强制锚定在 index 0
    return [SystemMessage(content=system_prompt)] + list(trimmed_dialogue)
