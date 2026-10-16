
# special approaches, all start with __

class Person:
    def __init__(self, name, age):
        self.hidden_name = name
        self.age = age


# 封装:hidden_name [藏] - increase the safety for data - 【 __name__ 】
# 如何获取修改 对象中 的属性
#   - getter
#   - setter