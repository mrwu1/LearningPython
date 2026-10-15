

class SafeDishItem:
    def __init__(self,dish_id:int,name:str,price:float):
        self._dish_id = dish_id
        self._name = name
        self._price = price

    @property
    def dish_id(self)->int:
        return self._dish_id

    @property
    def price(self)->float:
        return self._price

    @price.setter
    def price(self,value:float)->None:
        if value<0:
            raise ValueError("菜品价格必须大于 0！")
        self._price = value


if __name__=="__main__":
    dish = SafeDishItem(1,"ice cream",15.00)

    # 1. 正常访问（触发 @property getter）
    print("菜品 ID:", dish.dish_id)
    print("价格:", dish.price)

    # 2. 测试只读保护（dish_id 没有写 setter，尝试修改会被 Python 解释器严厉制止！）
    print("\n--- 测试篡改 ID ---")
    try:
        dish.dish_id = 999  # 预期直接报错：AttributeError: can't set attribute 'dish_id'
    except AttributeError as e:
        print("💡 成功防御篡改 ID:", e)

        # 3. 测试负数拦截
    print("\n--- 测试非法价格 ---")
    try:
        dish.price = -5.0
    except ValueError as e:
        print("💡 成功拦截负数价格:", e)
