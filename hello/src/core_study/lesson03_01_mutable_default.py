
def create_order_buggy(user_id:int,dishes:list=[]):
    dishes.append("cocla")
    return {"user_id": user_id, "dishes": dishes, "memory_id": id(dishes)} #❌

u1 = create_order_buggy(1)
print(f"ui:{u1},memory_id:{id(u1)}")

u2 = create_order_buggy(2)
print(f"ui:{u2},memory_id:{id(u2)}")

u3 = create_order_buggy(3)
print(f"ui:{u3},memory_id:{id(u3)}")

# 2. TODO: 企业级工业标准修复方案 ✅✅
# 黄金准则：函数的默认参数【严禁使用可变对象（list, dict, set）】！
# 正确写法：必须使用不可变哨兵值 None 作为默认值，在函数体内部动态创建！
def safe_create_order(user_id:int,dishes:list|None=None):
    if dishes is  None:
        dishes =[]
    dishes.append("wahaha")

    return  {"user_id": user_id, "dishes": dishes, "memory_id": id(dishes)}

s1 = safe_create_order(11)
print(s1)
s2 = safe_create_order(22)
print(s2)
s3 = safe_create_order(33)
print(s3)