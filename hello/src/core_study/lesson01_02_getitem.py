from core_study.lesson01_01_repr import DishItem


class SkyTakeoutMenu:
    def __init__(self,restaurant_name:str):
        self.restaurant_name = restaurant_name
        self._dishes:list[DishItem] =[]
        self._name_map:dict[str,DishItem] = {}

    def add_dish(self,dish:DishItem)->None:
        self._dishes.append(dish)
        self._name_map[dish.name] = dish

    def __len__(self)->int:
        #TODO: 外部支持len
        return len(self._dishes)

    def __getitem__(self, key:int|str|slice):
        # TODO: 2. 核心重载！
        if isinstance(key,str):
            result = self._name_map.get(key)
            if not result:
                raise KeyError(f"{key} not exists")
            return result
        if isinstance(key,int|slice):
            # result = self._dishes[key]
            # if not result:
            #     raise TypeError(f"{key} not support")
            # return result
            # 直接委托给原生列表，int 和 slice 统统原生支持！
            return self._dishes[key]
        return None
    def __call__(self, dish_name:str,quantity:int=1):
            # TODO: 让 menu 对象可以直接像函数一样被调用：menu("东坡肉", 2)
        dish = self._name_map.get(dish_name)
        if not dish:
            return f"❌ 下单失败：菜品{dish_name} not exist."
        total = dish.price * quantity
        return f"✅ 下单成功：已点 {quantity} 份【{dish.name}】，总计: ¥{total:.2f}"


if __name__ == "__main__":
    menu = SkyTakeoutMenu("sky takeout store")
    menu.add_dish(DishItem(101,"fried chicken",18.3))
    menu.add_dish(DishItem(102, "东坡肉", 58.0))
    menu.add_dish(DishItem(103, "牛肉羹", 26.0))

    print(len(menu))

    #把一个包含列表和字典的“复杂业务对象”直接当成“函数”调用 ‼️
    order1 = menu("东坡肉", 2)
    print(f"order1:{order1}")

 # 2. 验证 __getitem__ 的三种玩法
    print("下标查找 menu[0]      ->", menu[0])
    print("切片查找 menu[1:3]    ->", menu[1:3])
    print("名称索引 menu['东坡肉']->", menu["东坡肉"])