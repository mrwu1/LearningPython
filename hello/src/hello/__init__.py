def main() -> None:
    print("Hello from hello!")


def my_abs(x):
    if not isinstance(x, (int, float)):
        return TypeError("Input must be an integer or float")
    if x >= 0:
        return x
    else:
        return -x


# 计算x2
def power(x):
    return x * x


def power1(x, n):
    s = 1
    while n > 0:
        n = n - 1
        s = s * x
    return s


# 默认参数
def power2(x, n=2):
    s = 1
    while n > 0:
        n = n - 1
        s = s * x
    return s


# 可变参数
def calc(numbers):
    sum = 0
    for n in numbers:
        sum = sum + n * n
    return sum


calc([1, 2, 3, 4, 5])


def person(name, age, **kw):
    if "city" in kw:
        # 有city参数
        pass
    if "job" in kw:
        # 有job参数
        pass
    print("name:", name, "age:", age, "other:", kw)


person("Alice", 25, city="Beijing", job="Engineer")
# name: Alice age: 25 other: {'city': 'Beijing', 'job': 'Engineer'}


def fact(n):
    if n == 1:
        return 1
    return n * fact(n - 1)


print(fact(5))

# 切片
L = ["Michael", "Sarah", "Tracy", "Bob", "Jack"]
print(L[0:3])
print(L[:3])
print(L[1:3])
print(L[-2])

# 列表生成式
# goal: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
l = list(range(1, 11))
print(l)

# goal: [1x1, 2x2, 3x3, ..., 10x10]
m = []
for x in range(1, 11):
    m.append(x * x)
print(m)

# 列表生成式则可以用一行语句代替循环生成上面的list：
# 要生成的元素，放在 for 前面
n = [x * x for x in range(1, 11)]
print(n)

t = [x % 2 for x in range(1, 11)]
print(t)
# 还可以使用两层循环，可以生成全排列：
tt = [x * y for x in range(1, 11) for y in range(1, 11)]
print("double recursive", tt)

# tip: 运用列表生成式，可以写出非常简洁的代码。
# 例如，列出当前目录下的所有文件和目录名，可以通过一行代码实现：
from operator import ne
import os

f = [d for d in os.listdir(".")]
print(f)

# 两个或者多个变量
d = {"x": "A", "y": "B", "z": "C"}
for k, v in d.items():
    print(k, v)

# 转为小写
L = ["Hello", "World", "IBM", "Apple"]
tl = [s.lower() for s in L]
print(tl)

# if else
k = [x for x in range(1, 11) if x % 2 == 0]
print(k)

k1 = [x if x / 2 == 1 else x / 2 for x in range(1, 11)]
print(k1)
k2 = [x if x / 2 == 1 else x / 2 for x in range(1, 11) if x % 2 == 0]
print(k2)

# generator
g = (x * x for x in range(1, 11))
print(g)
# print(next(g))
# print(next(g))
# for loop
for n in g:
    print(n)


def odd():
    print("step 1")
    yield 1
    print("step 2")
    yield (3)
    print("step 3")
    yield (5)


o = odd()
print(next(o))
print(next(o))
print(next(o))
# print(next(o))

# 判断是否为iterator object
from collections.abc import Iterable

r1 = isinstance([], Iterable)
print("[]", r1)

r2 = isinstance({}, Iterable)
print("{}", r2)

r3 = isinstance(123, Iterable)
print("123", r3)

r4 = isinstance("Hello", Iterable)
print("Hello", r4)

r5 = isinstance(odd(), Iterable)
print("odd()", r5)
# 生成器都是Iterator对象，但list、dict、str虽然是Iterable，却不是Iterator

# iter
r6 = isinstance(iter([]), Iterable)
print("iter([])", r6)
