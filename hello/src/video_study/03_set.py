
s = {1,2,3,4,5,6,7,8,9}
s2 = {3,9,8,22,33,44}

#交集
r = s &s2
print(r)

#并集
r1 = s | s2
print(r1)

#差集
r2 = s  - s2
print(r2)

#异或集
r3 = s^s2
print(f"r3: {r3}")

#子集
r4 = s<=s2
print(f"r4: {r4}")

# print("hello",end='jsk',start="123")
