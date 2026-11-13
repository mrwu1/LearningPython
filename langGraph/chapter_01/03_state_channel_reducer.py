"""
================================================================================
【LangGraph 阶段一：基础状态机内核】第 3 课：状态通道（Channel）与合并器（Reducer）
================================================================================
【核心学习目标】：
1. 彻底搞懂并发写冲突：当多个并行节点在同一个超步试图写入【同一个字段】时会发生什么？
2. 理解为什么普通字段会报 `InvalidUpdateError`（默认通道是 LastValue 单值覆盖，不允许并发写入）。
3. 掌握 Reducer 的定义与挂载：使用 `typing.Annotated[数据类型, 合并函数]` 声明合并策略。
4. 掌握常用内置 Reducer：`operator.add`（用于 list 追加拼接）。
5. 掌握自定义 Reducer：编写字典合并函数（`merge_dict_reducer`），支持多节点并发上报元数据。
================================================================================
"""

import operator
import sys
from pathlib import Path
from pprint import pprint
from typing import TypedDict, Annotated

# 自动将项目根目录加入 sys.path，保证导包无误
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一步：编写自定义 Reducer 合并器函数
# ==============================================================================
# 【Reducer 函数编写黄金规范】：
# 1. 签名必须接收两个位置参数：(current_value, update_value)
#    - current_value: 当前全局 State 中该字段已有的值（可能是 None 或初始值）
#    - update_value: 节点本次返回的增量值
# 2. 返回值：合并后的全新状态值
# 3. 必须保证纯函数与不可变性：尽量避免在原有对象上原地破坏性修改，返回 copy 后的新对象更安全
def merge_dict_reducer(current_dict: dict, update_dict: dict) -> dict:
    """
    【自定义字典合并器】：
    当多个并行节点同时向 service_metadata 字典写入不同的子键值对时，
    本函数将它们浅合并到一个统一的字典中，避免互相覆盖或冲突崩溃。
    """
    merged = current_dict.copy() if current_dict else {}
    if update_dict:
        merged.update(update_dict)
    return merged


# ==============================================================================
# 第二步：使用 Annotated 声明包含 Reducer 的状态契约
# ==============================================================================
# 【核心语法】：Annotated[字段类型, 合并函数]
# - 未加 Annotated 的字段（如 final_status）：属于默认的 LastValue 通道，同一时间只能有一个节点写入。
# - 加了 Annotated 的字段（如 audit_logs、service_metadata）：属于 Reducer 通道，支持多个节点并发写！
class ComplianceOrderState(TypedDict):
    order_id: int

    # 【内置合并器 operator.add】：
    # 两个列表相加 [1] + [2] = [1, 2]，实现日志列表的自动追加拼接（Append）
    audit_logs: Annotated[list[str], operator.add]

    # 【自定义合并器 merge_dict_reducer】：
    # 多个节点并发写入字典的不同键时，自动做 dict.update() 合并
    service_metadata: Annotated[dict, merge_dict_reducer]

    # 【无 Reducer 的普通通道】：
    # 只能由一个节点串行修改，如果多个节点在同一步写入它，系统将直接报错 InvalidUpdateError！
    final_status: str


# ==============================================================================
# 第三步：定义并发计算节点（在同一个超步向相同字段并发写入）
# ==============================================================================
# 重点观察：security_scan_node 和 regulatory_compliance_node
# 它们会【完全并发执行】，并且【同时写入 audit_logs 和 service_metadata】！

def security_scan_node(state: ComplianceOrderState) -> dict:
    """【并行合规检查节点 1】：反欺诈与违禁品扫描。"""
    print("  * [Worker 1: 安全扫描] 发现订单合规，准备写入日志与元数据...")
    return {
        # 注意：这里返回的是一个包含单条记录的 list，Reducer 会把它与主状态 list 拼接
        "audit_logs": ["[SecurityScan] 反欺诈与禁运品检查通过 (置信度: 0.98)"],
        # 写入字典字段的一个子项
        "service_metadata": {"fraud_check_timestamp": "2026-10-17T13:30:00Z"}
    }


def regulatory_compliance_node(state: ComplianceOrderState) -> dict:
    """【并行合规检查节点 2】：食品安全税率与包装法合规校验。"""
    print("  * [Worker 2: 法规检查] 税率验证通过，准备同时写入日志与元数据...")
    return {
        # 同样并发返回一条日志，两个列表将被 operator.add 自动组合，不会丢失任何一条！
        "audit_logs": ["[Regulatory] 食品税与属地包装法核验完成 (适用税率: 6%)"],
        # 写入字典字段的另一个子项
        "service_metadata": {"tax_code": "TAX-FOOD-REG-01"}
    }


def finalize_order_node(state: ComplianceOrderState) -> dict:
    """【最终确认节点】：前序两个合规检查完成后，更新最终状态。"""
    print("\n---> [Finalize Node] 所有合规分支执行完毕，汇总结果并盖戳通过。")
    return {"final_status": "APPROVED_AND_CERTIFIED"}


# ==============================================================================
# 第四步：组装图拓扑
# ==============================================================================
def build_compliance_graph():
    builder = StateGraph(ComplianceOrderState)

    # 1. 注册节点
    builder.add_node("scan", security_scan_node)
    builder.add_node("compliance", regulatory_compliance_node)
    builder.add_node("finalize", finalize_order_node)

    # 2. 并发扇出：START 同时连接 scan 和 compliance
    builder.add_edge(START, "scan")
    builder.add_edge(START, "compliance")

    # 3. 屏障汇聚：两个并行检查全部指向 finalize
    builder.add_edge("scan", "finalize")
    builder.add_edge("compliance", "finalize")

    # 4. 终点
    builder.add_edge("finalize", END)

    return builder.compile()


# ==============================================================================
# 第五步：执行与验证
# ==============================================================================
if __name__ == "__main__":
    app = build_compliance_graph()
    print_graph_mermaid(app, "reducer")

    # 初始状态
    initial_state: ComplianceOrderState = {
        "order_id": 10086,
        "audit_logs": ["[Initial] 网关已接收订单请求，开始合规准入检测。"],
        "service_metadata": {"env": "production"},
        "final_status": "PENDING"
    }

    print("\n========== 开始执行并发写入测试 ==========")
    final_output = app.invoke(initial_state)

    print("\n========== 最终合并后的状态数据 ==========")
    print(f"1. 订单状态: {final_output['final_status']}")
    print("2. 完整审计日志 (operator.add 自动合并了 3 条记录):")
    for log in final_output["audit_logs"]:
        print(f"   -> {log}")
    print("3. 服务元数据 (merge_dict_reducer 自动合并了不同键值):")
    pprint(final_output["service_metadata"])
