
# api: {} / set

s = {1,2,3,4,5,6,7,8,9}
print(s,s.__class__)

s1 = set([1,2,3,4,5,6,7,8,9,1,2,3,4])
print(s1,s1.__class__)

# 空集合
s2 = set()

# set - 将序列和dict转为集合
s3 = set([12,34,24,56,78,90])
print(s3,type(s3))

s4 = set("hello")
print(s4,type(s4))

# in, not in
print( 'c' in s4)

# len
print(len(s4))

s4.add('hello')
print(s4)

# update
s4.update('hello')
print(s4)

# random - ❌
s4.pop()
print(s4)