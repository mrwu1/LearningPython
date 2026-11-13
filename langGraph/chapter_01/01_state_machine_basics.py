"""
================================================================================
【LangGraph 阶段一：基础状态机内核】第 1 课：状态机核心概念与循环工作流
================================================================================
【核心学习目标】：
1. 掌握 LangGraph 最核心的数据载体：TypedDict 定义的全局状态（State）。
2. 理解计算节点（Node）的纯函数契约：接收完整 State，返回部分增量（Partial Update）。
3. 掌握条件路由边（add_conditional_edges）：如何根据当前 State 决定下一步走向（分支或循环）。
4. 理解有环图（Cyclic Graph）：通过自动重试与参数自愈（Auto-Fix），打破传统 DAG 的单向限制。
================================================================================
"""

from pprint import pprint
from typing import TypedDict, Literal

# START 和 END 是 LangGraph 的两个系统保留虚拟节点：
# - START: 代表图的执行起点，当外界调用 app.invoke() 时，输入数据首先流经 START。
# - END: 代表图的最终终点，只要任何节点或条件路由导向 END，图的生命周期即刻结束并返回结果。
from langgraph.graph import StateGraph, START, END

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一步：定义全局状态（State Schema）
# ==============================================================================
# 【核心机制】：
# 1. State 是在图中所有节点之间流转的唯一上下文“白板”。
# 2. 在 LangGraph 中，推荐使用 Python 标准库的 TypedDict 来定义内部状态，性能最高且无序列化开销。
# 3. 每一个在 State 中声明的 key，都可以被节点读取；节点也可以返回对应 key 的新值来更新它。
class OrderState(TypedDict):
    order_id: str          # 订单唯一标识
    items: list[str]       # 订单商品列表
    total_price: float     # 订单总价（如果太高会触发风控）
    risk_score: float      # 风控模型评分（0-100，越高风险越大）
    retry_count: int       # 自动修复/重试次数计数器（用于防止死循环）
    status: str            # 订单生命周期状态（CREATED -> VALIDATED -> AUTO_FIXED -> END）


# ==============================================================================
# 第二步：定义计算节点（Compute Nodes）
# ==============================================================================
# 【节点函数黄金法则】：
# 1. 节点是一个普通的 Python 函数（或异步函数）。
# 2. 输入参数：接收当前超步（Superstep）最新的完整 State。
# 3. 输出参数：必须返回一个 dict！这个 dict 只需包含“你修改了的字段”（Partial Update 增量更新）。
# 4. 底层原理：LangGraph 会自动把节点返回的增量字典 shallow-merge（浅合并）覆盖回全局 State。

def validate_node(state: OrderState) -> dict:
    """
    【风控校验节点】：负责检查订单价格，并评估风控分数。
    - 如果订单价格 > 100 元，判定为高风险（85分）；
    - 否则判定为安全低风险（20分）。
    """
    print(f"\n---> [Node: validate_node] 当前订单价格: {state['total_price']}, 重试次数: {state['retry_count']}")
    
    if state['total_price'] > 100.00:
        calculated_risk = 85.0
    else:
        calculated_risk = 20.0

    # 只需要返回被修改的两个字段，LangGraph 会自动合并，其他未返回的字段（order_id、items 等）保持原样不变
    return {
        "risk_score": calculated_risk,
        "status": "VALIDATED"
    }


def auto_fix_node(state: OrderState) -> dict:
    """
    【自动修复节点】：风控未通过时的降级处理。
    - 给订单打 7 折（降价），从而帮助订单通过下一轮风控检查；
    - 同时自增重试计数器 retry_count，防止无限死循环。
    """
    current_retry = state["retry_count"] + 1
    # 打 7 折降价，降低暴险敞口以通过风控
    new_price = round(state["total_price"] * 0.7, 2)
    print(f"---> [Node: auto_fix_node] 触发自愈！订单打 7 折后新价格: {new_price}, 当前重试次数: {current_retry}")

    return {
        "total_price": new_price,
        "retry_count": current_retry,
        "status": "AUTO_FIXED"
    }


# ==============================================================================
# 第三步：定义条件路由边（Conditional Routing Edge）
# ==============================================================================
# 【路由函数工作机制】：
# 1. 路由函数不是节点，它不修改 State，只负责“看一眼当前状态，决定下一站往哪开”。
# 2. 返回值必须是字符串（目标节点的名称）或者特殊的 END 常量。
# 3. 这里展示了有环图的防御性编程：必须设计“熔断退出机制”（retry_count >= 2 强制结束），避免死循环消耗额度。

def should_continue(state: OrderState) -> Literal["auto_fix", END]:
    """
    【路由决策器】：
    - 风险分数 > 60 说明风控不达标：
      * 若重试次数 < 2，导向 "auto_fix" 节点进行降价自愈；
      * 若已重试达到 2 次，不再修复，直接走向 END 终止。
    - 风险分数 <= 60 说明风控已通过，直接走向 END 结束流程。
    """
    if state['risk_score'] > 60.0:  # 高风险，需要处理
        if state['retry_count'] < 2:
            print("=== [Router] 风控未通过，且重试次数未达上限 -> 转向自愈节点 [auto_fix]")
            return "auto_fix"
        else:
            print("=== [Router] 风控未通过，但重试已达上限 -> 熔断退出 [END]")
            return END
    
    print("=== [Router] 风控达标 -> 正常结束流程 [END]")
    return END


# ==============================================================================
# 第四步：组装图拓扑与编译（Graph Assembly and Compilation）
# ==============================================================================
def build_order_graph():
    # 1. 实例化图构建器，绑定主状态类型 OrderState
    builder = StateGraph(OrderState)

    # 2. 注册节点：add_node(节点名称标识, 对应的可执行函数)
    builder.add_node("validate", validate_node)
    builder.add_node("auto_fix", auto_fix_node)

    # 3. 静态边（Static Edge）：从系统起点 START 直接连到第一个工作节点 validate
    builder.add_edge(START, "validate")

    # 4. 条件路由边（Conditional Edge）：
    # 从 validate 节点出来后，调用 should_continue 函数做动态判断：
    # path_map 是可选的安全映射字典：声明可能的返回值对应哪些目标节点
    builder.add_conditional_edges(
        source="validate",
        path=should_continue,
        path_map={
            "auto_fix": "auto_fix",  # 当函数返回 "auto_fix" 时，跳转到 auto_fix 节点
            END: END                 # 当函数返回 END 时，结束运行
        }
    )

    # 5. 循环闭环边（Cyclic Edge）：
    # 从 auto_fix 修复完成后，重新连回 validate 再次校验！形成一个自动修复的有环图
    builder.add_edge("auto_fix", "validate")

    # 6. 编译图（Compile）：
    # 将声明式的拓扑结构编译为底层 Pregel 运行时的高性能可执行对象
    app = builder.compile()
    return app


# ==============================================================================
# 第五步：执行与验证（Execution and Verification）
# ==============================================================================
if __name__ == "__main__":
    # 编译生成图可执行对象
    app = build_order_graph()

    # 打印 Mermaid 状态机架构图（方便可视化阅读拓扑结构）
    print_graph_mermaid(app)

    # 初始化测试输入：总价 180.0 元的高额订单
    # 预期流转路径：
    # 1. START -> validate (180元 -> risk=85分)
    # 2. validate -> auto_fix (打7折 -> 126元，retry=1)
    # 3. auto_fix -> validate (126元仍然 > 100 -> risk=85分)
    # 4. validate -> auto_fix (再打7折 -> 88.2元，retry=2)
    # 5. auto_fix -> validate (88.2元 <= 100 -> risk=20分，通过！)
    # 6. validate -> END 顺利收敛
    initial_order: OrderState = {
        "order_id": "SKY-20261017-001",
        "items": ["Tomahawk Steak", "Vintage Red Wine"],
        "total_price": 180.0,
        "risk_score": 0.0,
        "retry_count": 0,
        "status": "CREATED"
    }

    print("\n========== 开始执行 LangGraph 状态机 ==========")
    final_state = app.invoke(initial_order)
    print("\n========== 最终全局状态输出 ==========")
    pprint(final_state)
