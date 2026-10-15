import json


class DishItem:
    def __init__(self,dish_id:int,name:str,price:float):
        self.dish_id = dish_id
        self.name = name
        self.price = price

    def __str__(self) -> str:
        # to user
        return json.dumps({"name":"辣子鸡丁","price":18.9},ensure_ascii= False)

    def __repr__(self) -> str:
        # to developer
        return f"DishItem(dish_id={self.dish_id},name={self.name!r},price={self.price})"


if __name__ == "__main__":
    d1 = DishItem(101, "辣子鸡丁", 38.0)
    d2 = DishItem(102, "东坡肉", 58.0)

    # 验证 1：单个打印，看是否触发 __str__
    print("【单个打印】：", d1)

    # 验证 2：列表排错，看是否触发 __repr__ 并清晰展示菜品详情
    print("【列表排错】：", [d1, d2])