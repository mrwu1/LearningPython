
def fn(a=1,b=2):
    print(f"fn(a,b): {a}, {b}")

fn(1,2)
fn(b=3,a=4)

# 形参- 函数内部重新赋值，不会改变外部变量

#解决方案：✅✅✅

def fn2(a):
    a[0] = 100
    print(f"fn2(a): {a},id(a): {id(a)}")

c=[1,2,3]
# fn2(c)
# fn2(c.copy()) ✅
fn2(c[:]) # ✅✅✅
print(c)

# 不定长参数 *  tuple - 只能有一个 ❌
def sum(*args):
    print(f"sum(*args): {args}, type(*args): {type(args)}")
    return len(args)

r =sum(1,2,3)
print(f"sum(r): {r}")