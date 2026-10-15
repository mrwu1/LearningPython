
# 通过 dict() 创建字典
d = dict(a=1, b=2, c=3)
print(d)

d1 = dict(a=4, b=5, c=6)
# d.pop("f")
# d.update(d1)
# print(d)

# copy - 独立-只针对基本类型
d2 = d.copy()
print(d2,id(d2))
print(d1,id(d1))

# 遍历
for k,v in d.items():
    print(k,v)

for k in d.keys():
    print(k)

for v in d.values():
    print(v)