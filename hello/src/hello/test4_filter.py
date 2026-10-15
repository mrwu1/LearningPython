def is_odd(n):
    return n % 2 == 1


r = list(filter(is_odd, [1, 2, 4, 5, 6, 9, 10, 15]))
# 结果: [1, 5, 9, 15]
print(r)

sequence1: list[int] = [1, 2, 4, 5, 6, 9, 10, 15]
r1 = filter(lambda x: x % 2 == 1, sequence1)
print(list(r1))


def not_empty(s):
    return s and s.strip()


r = list(filter(not_empty, ["hello", "world", "", "python", "   "]))
print(r)


# 无限序列
def _odd_iter():
    n = 1
    while True:
        n = n + 2
        yield n


# 筛选函数
def _not_divisible(n):
    return lambda x: x % n > 0


# 最后，定义一个生成器，不断返回下一个素数：
def primes():
    yield 2
    it = _odd_iter()  # 初始序列
    while True:
        n = next(it)  # 返回序列的第一个数
        yield n
        it = filter(_not_divisible(n), it)  # 构造新序列


# use:
# 打印100以内的素数:
for n in primes():
    if n < 100:
        print(n)
    else:
        break


# 回数是指从左向右读和从右向左读都是一样的数，例如12321，909。请利用filter()筛选出回数：
def is_palindrome(n):
    s = str(n)
    return s == s[::-1]


r = list(filter(is_palindrome, range(1, 10)))
print(r)

# 打印名称
fname: str = primes.__name__
print(fname)


# enhance it: ，在函数调用前后自动打印日志,但又不希望修改now()函数的定义，称为 “Decrator” [类似切面]
# core: that is a function which return a function
# 版本1:
def log(func):
    def wrapper(*args, **kwargs):
        print(f"calling {func.__name__}")
        return func(*args, **kwargs)

    return wrapper


import functools


# 版本2：
def log1(func):
    @functools.wraps(func)
    def wrapper(*args, **kw):
        print("call %s():" % func.__name__)
        return func(*args, **kw)

    return wrapper


import functools


# 版本3：
def log2(text):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            print("%s %s():" % (text, func.__name__))
            return func(*args, **kw)

        return wrapper

    return decorator


@log2("execute")
def now():
    print("2024-6-1")


now()
