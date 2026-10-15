from typing import TypedDict

from langgraph.graph import START, END, StateGraph
from typing_extensions import Literal


### 业务场景：

# 用 LangGraph 状态图重构外卖订餐链路：
#
# 1. 定义全局状态 TakeoutState（使用 Python 原生 TypedDict，记录用户问题、菜品ID、购买数量、库存结果、订单号、最终回答）；
# 2. 定义 3 个功能明确的纯函数节点（Nodes）：
# • parse_intent_node：从用户问题中提取结构化参数；
# • check_stock_node：查询本地模拟数据库，记录真实库存；
# • create_order_node：如果库存充足，执行真实扣减并生成订单号；
# 3. 定义确定性条件边（Conditional Edge）：
# • 如果库存不足，直接路由到结束；如果充足，精准路由到下单节点。

# first: define a global sharing state - dto
class TakeoutState(TypedDict):
    user_query:str
    dish_id:int
    count:int
    address:str
    stock:int
    order_id:str|None
    final_reply:str
 # 模拟数据库
MOCK_DISH_DB = {
    101: {"name": "招牌香辣鸡腿堡", "price": 25.0, "stock": 10},
    102: {"name": "黄金脆薯条", "price": 12.0, "stock": 0},  # 缺货
}

# second: define the business dealing nodes
def parse_intent_node(state:TakeoutState)->dict:
    """【节点 1】：意图解析节点 (此处可调大模型结构化提取，这里用规则做演示)"""
    print("\n📍 [Node 1: 意图解析] 正在分析用户指令...")
    # 假设从自然语言提取到了确定性参数（在实际中这里可以用 Pydantic 做提取）
    return{
        "dish_id":101,
        "count":2,
        "address":"中关村南大街1号院"
    }

def check_stock_node(state:TakeoutState)->dict:
    """【节点 2】：库存查询节点 (纯确定性后端查询，绝不依赖大模型自由发挥)"""
    dish_id = state["dish_id"]
    print(f"\n📍 [Node 2: 库存查询] 正在查询菜品 {dish_id} 的实时数据库库存...")
    dish = MOCK_DISH_DB.get(dish_id, {"stock": 0})
    real_stock = dish["stock"]
    print(f"   查询结果: 菜品={dish.get('name')}, 当前可用库存={real_stock}")
    return {"stock": real_stock}

def create_order_node(state:TakeoutState)->dict:
    """【节点 3】：真正下单节点 (只有在确定有库存时才会被图引擎调度)"""
    print(f"\n📍 [Node 3: 交易下单] 库存充足，正在执行真实扣减并生成订单...")
    # 真正扣减库存
    MOCK_DISH_DB[state["dish_id"]]["stock"] -= state["count"]
    order_id = "ORD_20261014_888"
    print(f"   下单成功！生成正式订单号: {order_id}")
    return {
        "order_id": order_id,
        "final_reply": f"已成功为您下单 2 份香辣鸡腿堡！订单号: {order_id}，送往 {state['address']}。"
    }

def out_of_stock_node(state:TakeoutState):
    """【节点 4】：缺货兜底节点"""
    print(f"\n📍 [Node 4: 缺货告警] 触发库存不足分支！")
    return {
        "order_id": None,
        "final_reply": f"非常抱歉，您想购买的菜品当前库存不足（仅剩 {state['stock']} 份），无法完成下单。"
    }

# third: define edges with confirming conditions
def stock_check_condition(state:TakeoutState)->Literal["has_stock","no_stock"]:
    """【条件决策函数】：100% 确定性的代码路由，彻底消除大模型乱序风险！"""
    if state["stock"] >= state["count"]:
        return "has_stock"
    return "no_stock"


# fourth: create and compile a state graph - stateGraph

def build_takeout_graph():
    # 1. initialize a generator
    builder = StateGraph(TakeoutState)
    # 2. register all nodes:
    builder.add_node("parse_intent",parse_intent_node)
    builder.add_node("check_stock",check_stock_node)
    builder.add_node("create_order", create_order_node)
    builder.add_node("out_of_stock", out_of_stock_node)

    # 3. organize the edges
    # START -> parse_intent -> check_stock
    builder.add_edge(START,"parse_intent")
    builder.add_edge("parse_intent","check_stock")

    # core: take different branch by the stock count. ‼️
    builder.add_conditional_edges(
        "check_stock",
        stock_check_condition,
        {
            "has_stock":"create_order", # path1
            "no_stock":"out_of_stock" # path2
        }
    )

    # then, workflow:
    builder.add_edge("create_order",END)
    builder.add_edge("out_of_stock", END)

    # finally:
    return builder.compile()

if __name__=="__main__":
    print("=== 构建并执行 LangGraph 外卖确定性工作流 ===")
    app_graph = build_takeout_graph()
    # 1. input a value
    initial_state={
        "user_query": "帮我订 2 份 101 号菜品送去中关村南大街1号院"
    }

    # 2.invoke graph
    final_state = app_graph.invoke(initial_state)

    print(final_state)
















