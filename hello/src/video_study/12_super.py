

class Animal:
    def __init__(self, name):
        self._name = name
    @property
    def name(self):
        return self._name
    @name.setter
    def name(self, value):
        self._name = value

class Dog(Animal):
    def __init__(self, name,age):
        # 动态获取 ✅，且，不需要传递 self
        super().__init__(name)

        # issue: Animal is sticky ❌ 耦合了
        # Animal.__init__(self, name)
        self._age = age


dog = Dog("小坡",3)
