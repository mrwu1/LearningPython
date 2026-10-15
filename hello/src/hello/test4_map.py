from functools import reduce
from turtle import st


def f(x):
    return x * x


# 使用 map 函数对列表中的每个元素进行平方运算
numbers = [1, 2, 3, 4, 5]
r = map(f, numbers)
print(list(r))


# reduce
def add(x, y):
    return x + y


numbers1 = [1, 2, 3]

r1 = reduce(add, numbers1)
print(r1)

# sum 内置函数直接实现
r2 = sum(numbers1)
print(r2)


# 但是如果要把序列[1, 3, 5, 7, 9]变换成整数13579，reduce就可以派上用场：
def fn(x, y):
    return x * 10 + y


r3 = reduce(fn, [1, 3, 5, 7, 9])
print(r3)

# reduce + map
from functools import reduce

DIGITS = {
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
}


def str2int(s):
    def fn(x, y):
        return x * 10 + y

    def char2num(s):
        return DIGITS[s]

    return reduce(fn, map(char2num, s))


# 简化版本
from functools import reduce


def char2num(s):
    return DIGITS[s]


def str2int2(s):
    return reduce(lambda x, y: x * 10 + y, map(char2num, s))


# 利用map()函数，把用户输入的不规范的英文名字，变为首字母大写，其他小写的规范名字。
# 输入：['adam', 'LISA', 'barT']，输出：['Adam', 'Lisa', 'Bart']：


def testfn(x: str):
    firstletter: str = x[0]
    otherletters: str = x[1:]
    return firstletter.upper() + otherletters.lower()


test: list[str] = ["adam", "LISA", "barT"]
result = map(testfn, test)
print(list(result))
