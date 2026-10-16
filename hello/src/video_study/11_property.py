
# rule: ✅
class Person:
    def __init__(self, name):
        self._name = name

    @property #get方法转为对象的属性
    def name(self):
        return self._name

    @name.setter # @属性名.setter
    def name(self, value):
        self._name = value

#test
p = Person("小米")
print(p.name)
