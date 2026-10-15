from hello.test4_map import fn


#参数的解包
def f(a,b,c):
    return f"f: {a}, b: {b}, c: {c}"

#tuple
t = (1,2,3)

# 单星 * ✅
r0 = f(*t)
print(r0)

#dict
d={'a':51,'b':42,'c':23}

# 解包 双星 ** ✅✅
r = f(**d)
print(r,type(r))