import functools


def retry(max_retries: int = 3):
    # 第一层：接收装饰器自身的参数 (max_retries)
    def decorator(func):
        # 第二层：接收被装饰的目标函数 (func)
        @functools.wraps(func)  # 关键：保留原函数的名字、注释等元信息
        def wrapper(*args, **kwargs):
            # 第三层：接收调用目标函数时传入的实际参数 (*args, **kwargs)
            #  在这里写执行前逻辑、异常捕获、重试循环
            return func(*args, **kwargs)

        return wrapper

    return decorator
