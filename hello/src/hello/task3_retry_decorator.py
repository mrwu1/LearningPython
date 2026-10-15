#   ### 业务背景：

#   调用大模型或外网接口时，网络抖动（如超时、503）极常见。我们必须写一个通用的重试装饰器
#   @retry_on_failure，用来自动捕获异常并平滑重试。

#   1. 实现带参数装饰器 @retry_on_failure(max_retries: int = 3, delay: float = 1.0)：
#       • 自动捕获函数执行中的异常；
#       • 打印重试告警日志（第几次重试、报错信息是什么）
#       • 等待 delay 秒后再次重试（使用 time.sleep）
#       • 超过最大重试次数 max_retries 后，将最后一次的异常原样抛出（raise）
#       • 必须使用 @functools.wraps(func)。

from datetime import time
from functools import wraps
import functools
from typing import Any, Any, Callable


# ----------------- template start -----------------
def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    # 第一层：接受 decrator自身的参数
    def decrator(func):
        # 第二层：接受被装饰的 目标函数 func
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            #  第三层：接受调用目标函数时传入的 实际参数
            # TODO: 可以在这里写 “执行前逻辑，异常捕获，重试循环“
            return func(*args, **kwargs)

        return wrapper

    return decrator


# ----------------- template end -----------------
def retry_on_mechaism(max_retries: int = 3, delay: float = 1.0):
    def decrator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args, **kwargs) -> Any:
            # TODO: 可以在这里写 “执行前逻辑，异常捕获，重试循环“
            last_exception = None
            for i in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if i < max_retries:
                        print(
                            f"[警告] 捕获异常: {e}，"
                            f"正在等待 {delay}s 后进行第 {i}/{max_retries} 次重试..."
                        )
                        time.sleep(delay)
                    else:
                        print(
                            f"[严重错误] 已达最大重试上限 ({max_retries} 次)，重试耗尽！"
                        )
            if last_exception:
                raise last_exception

        return wrapper

    return decrator

    #   2. 测试目标函数 call_unstable_llm_api()：
    #       • 用一个计数器模拟前两次调用失败（抛出 ConnectionError("网络抖动，API连接失败")），
    #         第三次调用成功返回结果。
    # --- 模拟测试环境 ---


attempt_counter = 0


def call_unstable_llm_api(prompt: str) -> str:
    """模拟一个经常发生网络波动的外部大模型 API"""
    global attempt_counter
    attempt_counter += 1
    print(f"--> [发起请求] 第 {attempt_counter} 次尝试连接大模型，提示词: '{prompt}'")

    # 模拟前 2 次都抛出网络连接异常
    if attempt_counter < 3:
        raise ConnectionError(
            f"HTTP 503: 服务端连接超时 (模拟第 {attempt_counter} 次失败)"
        )

    # 第 3 次成功返回
    return f"【模型响应成功】：已为您查询到关于 '{prompt}' 的相关结果。"


if __name__ == "__main__":
    print("=== 开始执行带重试机制的函数调用 ===\n")
    try:
        response = call_unstable_llm_api("查询今日热门菜品")
        print("\n最终返回结果:\n", response)
    except Exception as e:
        print("\n最终重试耗尽，调用彻底失败:", e)

call_unstable_llm_api("查询今日热门菜品")
