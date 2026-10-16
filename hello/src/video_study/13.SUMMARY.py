

class A(object):

    # 类属性：
    #   - 可以通过类或者 instance 的访问
    #   - 修改：只能通过 类对象 ✅
    count = 0

    # instance方法：
    #   - self 为第一个参数的方法，都是 instance 方法
    #   - instance 方法调用时，python会将 调用对象作为 self 传入
    def __init__(self, name):
        self._name = name

    # instance
    def test(self):
        print(self._name)

    # 类方法
    #   - 类内部使用 @classmethod 来修饰的方法
    #   - 第一个参数是：cls,也会被自动传递， cls 就是当前的类对象

    # 区别：第一个参数不一样，其他都一样
    @classmethod
    def test_2(cls):
        print(cls)

    # 静态方法 - 与当前类无关的方法，只是保存到 类中的一个方法 ⚠️。【一般工具方法】
    @staticmethod
    def test_3():
        print("static")


a = A("幂")
print(a.count)

a.count = 22
# A.count = 1
print(A.count)

a.test()