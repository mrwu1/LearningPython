

def mul(a, b):
    return a * b

# print log

def decorator(a, b):
    print("start execute this function")
    mul(a, b)
    print("end execute this function")

decorator(1, 2)

# ⚠️⚠️⚠️  a Decorator
def begin_end(old):
    # 创建一个新函数
    def new_function(*args, **kwargs): #装包成 dict
        print("begin execute this function")
        # 调用被扩展的函数
        r = old(*args, **kwargs) # 拆包成 keyword
        print("end execute this function")
        return r
    return new_function #返回新函数

# normal use ⚠️❌
f = begin_end(mul)
s = f(3,4)
print(s)

# recommend use ✅✅✅
@begin_end
def say_hello():
    print("hello world")

say_hello()
#⚠️：multiple decorators , from inside to outside