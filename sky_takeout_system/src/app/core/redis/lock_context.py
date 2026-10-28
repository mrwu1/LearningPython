import contextvars
from typing import Optional

# 关键修复：
# 1. default=None（避免可变默认值陷阱，修复原 defult={} 拼写错误）
# 2. 每个 context 独立 dict，不会串锁
_reentrant_token_ctx: contextvars.ContextVar[Optional[dict[str, str]]] = \
    contextvars.ContextVar("reentrant_tokens", default=None)


def get_ctx_tokens() -> dict[str, str]:
    """返回当前 context 的 token 字典；不存在则惰性初始化。"""
    ctx = _reentrant_token_ctx.get()
    if ctx is None:
        ctx = {}
        _reentrant_token_ctx.set(ctx)
    return ctx


def set_ctx_token(resource_key: str, token: str) -> None:
    ctx = get_ctx_tokens().copy()
    ctx[resource_key] = token
    _reentrant_token_ctx.set(ctx)


def pop_ctx_token(resource_key: str) -> None:
    ctx = get_ctx_tokens().copy()
    ctx.pop(resource_key, None)
    _reentrant_token_ctx.set(ctx)