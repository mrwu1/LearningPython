
# filter()  - 从序列中过滤出符合条件的元素，保存到一个新的序列

# api: filter(fn,m)
# return: iterator
# list(r)

#issue: 单独定义函数 ，不推荐 ❌

#solve: 匿名函数 - lambda 表达式
# grammar: lambda 参数列表：返回值

def fn(a,b):
    return a+b

lambda a,b:a+b

print((lambda a, b: a + b)(3, 5))

#filter: sweet - candy

r =filter(lambda i:i%2==0,[1,2,3])
print(list(r))

#map
r1 = map(lambda i:i+1,[4,2,3])
print(list(r1))

#sort
l = [3,2,1,6]
l.sort()
print(l)