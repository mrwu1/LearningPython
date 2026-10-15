
class PositiveNumber:
    """
            可复用的正数校验描述符
            对标 Java: @Positive 校验器
    """
    def __set_name__(self, owner: object, name: str)->None:
        # 当在类中声明 price = PositiveNumber() 时，Python 自动调用这里
        # name 就是 "price"，我们自动给内部私有存储加上下划线 "_price"
        self.storage_name =f"_{name}"

    def __get__(self, instance, owner):
        # 如果是通过类本身访问 (Dish.price)，直接返回描述符对象本身
        if instance is None:
            return self
        # 通过实例访问 (dish.price)，从实例的底层字典里取出真实值
        return getattr(instance,self.storage_name,None)

    def __set__(self, instance:object, value:float)->None:
        # TODO: 核心写拦截！
        if value<0:
            raise ValueError(f"❌ 字段 {self.storage_name[1:]} 必须大于 0！")
        setattr(instance,self.storage_name,value)

# magic time:
class Dish:
    price = PositiveNumber()
    cost = PositiveNumber()

    def __init__(self,name:str,price:float ,cost:float):
        self.name = name
        self.price  = price  # 自动触发 price 的 __set__ 校验
        self.cost = cost # 自动触发 cost 的 __set__ 校验

if __name__ == "__main__":
     # 1. create an object
    duck = Dish("grilled duck",36.00,25.00)
     # 2. update it
    duck.price = 49.90
    print(f"调价后售价: ¥{duck.price}")

     # 3. valid price
    try:
         duck.price=-9
    except ValueError as e:
         print(f"e:{e}")