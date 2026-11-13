"""
================================================================================
【LangGraph 阶段四：持久化与双层记忆底座】第 2 课：企业级多租户数据隔离与子图命名空间（checkpoint_ns）
================================================================================
【核心学习目标】：
1. 掌握多租户物理级隔离规范：
   - 企业级规范 thread_id 生成结构：`{tenant_id}:{user_id}:{session_id}`；
   - 证明即使共享同一个 SQLite/PostgreSQL 数据库，不同租户之间也绝不串台泄露。
2. 掌握子图嵌套（Subgraph Composition）核心写法：
   - 将一个完整编译后的子图（Compiled Graph）作为普通节点挂载到父图中：✅✅✅
     `parent_builder.add_node("internal_risk_subgraph", risk_subgraph)`。
3. 深入理解分层命名空间 `checkpoint_ns`：
   - 父图的状态存储在根命名空间（""）；
   - 子图的状态由 LangGraph 自动存入专属命名空间（如 "internal_risk_subgraph:..."）；
   - 实现了父子图状态独立保存、互不覆盖污染。
================================================================================
"""

import operator
import sqlite3
import sys
from pathlib import Path
from typing import TypedDict, Annotated

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph


# ==============================================================================
# 第一部分：子图定义（Child Subgraph）
# ==============================================================================
# 子图拥有完全独立于父图的状态模型 SubgraphState
class SubgraphState(TypedDict):
    """子图专属工作状态：仅用于内部风控合规审查。"""
    audit_notes: Annotated[list[str], operator.add]


def risk_audit_node(state: SubgraphState) -> dict:
    """【子图工作节点】：执行反洗钱与制裁名单核验。"""
    print("      [子图节点: audit_worker] 执行制裁名单与反洗钱审查 -> 通过")
    return {"audit_notes": ["风控核验通过：未发现受制裁主体或洗钱嫌疑。"]}


def build_risk_subgraph():
    """编译并产出子图实例。"""
    sub_builder = StateGraph(SubgraphState)
    sub_builder.add_node("audit_worker", risk_audit_node)

    sub_builder.add_edge(START, "audit_worker")
    sub_builder.add_edge("audit_worker", END)
    # 返回编译后的子图对象（CompiledGraph）
    return sub_builder.compile()


# ==============================================================================
# 第二部分：父图定义（Parent Graph）
# ==============================================================================
# 父图状态模型 ParentState（供客服与主流程流转）
class ParentState(TypedDict):
    customer_notes: Annotated[list[str], operator.add]


def customer_service_node(state: ParentState) -> dict:
    """【父图节点 1】：处理直接的客户订单登记。"""
    print("  ---> [父图节点: customer_service] 客户订单需求登记完成")
    return {"customer_notes": ["客户工单与需求登记完成。"]}


def build_parent_graph(checkpointer: SqliteSaver):
    # 1. 实例化子图对象
    risk_subgraph = build_risk_subgraph()

    parent_builder = StateGraph(ParentState)
    parent_builder.add_node("customer_service", customer_service_node)

    # 2. 【核心 API：挂载子图为普通节点】
    # 在父图中，子图被当做一个黑盒节点进行调度！
    parent_builder.add_node("internal_risk_subgraph", risk_subgraph)

    # 3. 编排时序边
    parent_builder.add_edge(START, "customer_service")
    parent_builder.add_edge("customer_service", "internal_risk_subgraph")
    parent_builder.add_edge("internal_risk_subgraph", END)

    # 4. 挂载持久化检查点编译
    return parent_builder.compile(checkpointer=checkpointer)


# ==============================================================================
# 第三部分：多租户隔离与分层命名空间检验
# ==============================================================================
if __name__ == "__main__":
    # 使用独立数据库文件
    db_connection = sqlite3.connect("checkpoints_sub.db", check_same_thread=False)
    checkpointer = SqliteSaver(db_connection)
    app = build_parent_graph(checkpointer)

    # --------------------------------------------------------------------------
    # 1. 企业级多租户规范：三段式复合 thread_id
    # 格式规范：{租户ID}:{用户ID}:{会话ID}
    # --------------------------------------------------------------------------
    tenant_apple_thread = "TENANT_APPLE:USER_ALICE:SESSION_1001"
    tenant_tesla_thread = "TENANT_TESLA:USER_BOB:SESSION_2002"

    config_apple = {"configurable": {"thread_id": tenant_apple_thread}}
    config_tesla = {"configurable": {"thread_id": tenant_tesla_thread}}

    print("\n========== 第一阶段：执行苹果公司（Apple）租户工作流 ==========")
    app.invoke({"customer_notes": ["苹果公司订单：采购 50,000 颗 M4 芯片。"]}, config=config_apple)

    print("\n========== 第二阶段：执行特斯拉（Tesla）租户工作流 ==========")
    app.invoke({"customer_notes": ["特斯拉订单：采购 1,000 台 Optimus 机器人。"]}, config=config_tesla)

    # --------------------------------------------------------------------------
    # 2. 严格核验多租户数据物理隔离（防止数据跨租户泄露）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("========== 第三阶段：验证租户数据完全隔离 ==========")
    apple_state = app.get_state(config_apple)
    tesla_state = app.get_state(config_tesla)

    print(f"🍏 苹果租户会话数据: {apple_state.values['customer_notes']}")
    print(f"🚗 特斯拉租户会话数据: {tesla_state.values['customer_notes']}")
    print("【隔离结论】：两者在同一个数据库中完全独立，互无交叉！")
    print("=" * 65)

    # --------------------------------------------------------------------------
    # 3. 探秘子图层级命名空间（checkpoint_ns）
    # --------------------------------------------------------------------------
    print("\n========== 第四阶段：探秘子图检查点命名空间 (checkpoint_ns) ==========")
    # 查询 Apple 线程下的所有检查点记录（包含父图和子图）
    subgraph_snapshots = list(app.get_state_history(config_apple))

    print(f"线程 [{tenant_apple_thread}] 录制了 {len(subgraph_snapshots)} 条检查点快照：\n")
    for idx, snapshot in enumerate(subgraph_snapshots):
        # checkpoint_ns: 空字符串代表父图根空间；带路径的代表子图私有空间
        ns = snapshot.config["configurable"].get("checkpoint_ns", "root")
        node_checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
        print(f"  [{idx}] 命名空间 (Namespace): {repr(ns):<35} | 检查点编号: {node_checkpoint_id}")
