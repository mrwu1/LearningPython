# 掩饰magic方法的用法，并添加详细注释

class Person:
    def __init__(self,name:str,age:int):
        self._name = name
        self._age = age
    # 用法： 打印 对象的时候调用
    def __str__(self):
        pass
    # 用法：
    def __repr__(self):
        pass

    def __lt__(self,other):
        return self._age < other._age
    def __gt__(self,other):
        return self._age > other._age
    def __eq__(self,other):
        return self._age == other._age
    def __le__(self,other):
        return self._age <= other._age
    def __ge__(self,other):
        return self._age >= other._age
    def __add__(self,other):
        return self._age + other._age
    def __sub__(self,other):
        return self._age - other._age
    def __mul__(self,other):
        return self._age * other._age
    def __truediv__(self,other):
        return self._age / other._age
    def __floordiv__(self,other):
        return self._age // other._age
    def __mod__(self,other):
        return self._age % other._age
    def __pow__(self,other):
        return self._age ** other._age
    def __rmod__(self,other):
        return self._age % other._age
    def __rmul__(self,other):
        return self._age * other._age

    def __rdiv__(self,other):
        return self._age / other._age
    def __rfloordiv__(self,other):
        return self._age // other._age

