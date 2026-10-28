# 只负责通过 inspect 反射动态解析被注解函数的入参，并将参数填入 Key 模板，实现业务与锁的完全解耦：
import functools
import inspect

from app.core.redis.mutex import RedisLock
from app.core.redis.redisson_lock import RedissonLock


def with_distributed_lock(
        key_template: str,
        lease_seconds: int=15,
        acquire_timeout: float=3.0
):
    """
            AOP Decorator for Distributed Locking:
            Extracts dynamic variables from func arguments to construct resource lock keys.
            Example:
                @with_distributed_lock("order:{order_number}")
                async def cancel_order(session, order_number: str): ...
    """
    def decorator(func):
        # inspect- 通过 Python 底层反射，像 X 光一样扫描到实参名字叫 order_number，值是 "ORD_001"。
        sig = inspect.signature(func)
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
             # 绑定运行时实参，提取模板所需变量 (如 order_number, dish_name)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            resource_key = key_template.format(**bound_args.arguments)
            async with RedissonLock(
                     resource_key=resource_key,
                     lease_seconds=lease_seconds,
                     acquire_timeout=acquire_timeout,
             ): # 👈 你的业务代码被夹在中间！
                return await func(*args, **kwargs)
        return wrapper
    return decorator