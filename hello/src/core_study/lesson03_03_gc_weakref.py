import weakref


class Kitchen:
    def __init__(self,name:str):
        self.name = name
        self.chef = None
    def __del__(self):
        print(f"🗑️ 内存释放：厨房【{self.name}】已被垃圾回收！")

class Chef:
    def __init__(self,name:str,kitchen:Kitchen):
        self.name = name
        self.kitchen_ref = weakref.ref(kitchen) # weak REF

    @property
    def kitchen(self):
        ## 加一对括号 () 解包出真实对象！ __call__
        return self.kitchen_ref()

    def __del__(self):
        print(f"🗑️ 内存释放：主厨【{self.name}】已被垃圾回收！")


if __name__ == "__main__":
    print("--- 1. 创建厨房与主厨互相绑定 ---")
    k = Kitchen("总店中央后厨")
    c = Chef("张大厨", k)
    k.chef = c  # 厨房持有主厨

    # 验证弱引用是否能正常读取厨房
    print(f"张大厨所在的厨房是: {c.kitchen.name}")

    print("\n--- 2. 销毁外部变量引用 ---")
    del k
    del c

    print("\n--- 3. 程序结束 ---")