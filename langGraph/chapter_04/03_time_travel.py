"""
================================================================================
【LangGraph 阶段四：持久化与双层记忆底座】第 3 课：时间旅行（Time Travel）与状态分支分叉（Forking）
================================================================================
【核心学习目标】：
1. 掌握 LangGraph 最革命性的特性：时间旅行（Time Travel）与人类干预回滚。
2. 理解类 Git 的不可变状态树（Immutable State Tree）：
   - 每次节点执行都会沉淀一个拥有独立 `checkpoint_id` 的只读快照；
   - 过去的快照永远不会被破坏，状态回滚实际是在旧节点上分叉（Fork）出一条全新的时间线。
3. 掌握核心 API：
   - `app.get_state_history(config)`: 查看整个会话的演进历史（相当于 `git log`）；
   - `app.update_state(config, values={...}, as_node="...")`: 在历史的某个时间点注入人工修正数据；
   - `app.invoke(None, config=forked_config)`: 从分叉点恢复图的执行（入参传 `None` 表示从已有检查点直接唤醒）。
================================================================================
"""

import sys
import sqlite3
from pathlib import Path
from typing import TypedDict, Literal

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from loguru import logger

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一步：定义合同审批状态契约（State Schema）
# ==============================================================================
class ContractState(TypedDict):
    contract_title: str     # 合同标题
    amount_usd: float       # 合同金额（美元）
    audit_status: str       # 审计状态：PENDING_AUDIT / REJECTED / APPROVED
    final_disposition: str  # 归档结果


# ==============================================================================
# 第二步：定义审批流节点与条件路由
# ==============================================================================

def drafter_node(state: ContractState) -> dict:
    """【起草节点】：录入初始合同信息，标记为待审计。"""
    print(f"\n---> [Node: drafter] 合同《{state['contract_title']}》起草完成，提交风控...")
    return {"audit_status": "PENDING_AUDIT"}


def risk_audit_node(state: ContractState) -> dict:
    """
    【风控审批节点】：
    - 若金额 > 50,000 美元，严格判定超标驳回；
    - 否则审批通过，准许签署。
    """
    amount = state["amount_usd"]
    print(f"---> [Node: risk_audit] 正在审核合同金额: ${amount:,.2f} ...")
    if amount > 50000.0:
        print("  ❌ 金额超标（> $50,000）！审批驳回，合同作废。")
        return {
            "audit_status": "REJECTED",
            "final_disposition": "CONTRACT_ABORTED"
        }
    else:
        print("   金额合规！审批通过，准予签署。")
        return {
            "audit_status": "APPROVED",
            "final_disposition": "READY_FOR_SIGNATURE"
        }


def router_after_audit(state: ContractState) -> Literal["archiver", END]:
    """【条件路由】：通过则走向归档，驳回则直接结束。"""
    if state["audit_status"] == "APPROVED":
        return "archiver"
    return END


def archive_node(state: ContractState) -> dict:
    """【归档节点】：归档通过审批的合同。"""
    print("---> [Node: archiver] 合同已完成电子签章并归档至法务云。")
    return {"final_disposition": "ARCHIVED_SUCCESSFULLY"}


# ==============================================================================
# 第三步：组装图拓扑
# ==============================================================================
def build_contract_graph(checkpointer: SqliteSaver):
    builder = StateGraph(ContractState)
    builder.add_node("drafter", drafter_node)
    builder.add_node("risk_audit", risk_audit_node)
    builder.add_node("archiver", archive_node)

    builder.add_edge(START, "drafter")
    builder.add_edge("drafter", "risk_audit")
    builder.add_conditional_edges("risk_audit", router_after_audit)
    builder.add_edge("archiver", END)

    return builder.compile(checkpointer=checkpointer)


# ==============================================================================
# 第四步：时间旅行演练（Time-Travel in Action）
# ==============================================================================
if __name__ == "__main__":
    db_connection = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(db_connection)
    app = build_contract_graph(checkpointer)

    session_config = {"configurable": {"thread_id": "CONTRACT_WORKFLOW_2026"}}

    # --------------------------------------------------------------------------
    # 阶段 1：初次运行（人为填错数据：金额多填了两个零，触发风控驳回！）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【第一阶段】：初次运行，因人工失误输入了 $1,000,000 巨额数值...")
    initial_payload = {
        "contract_title": "企业云迁移框架协议",
        "amount_usd": 1000000.0,  # 人工手误！远超 50,000 限制
        "audit_status": "UNINITIALIZED",
        "final_disposition": "IN_PROGRESS"
    }
    app.invoke(initial_payload, config=session_config)

    # --------------------------------------------------------------------------
    # 阶段 2：调取检查点时光树（相当于执行 git log）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【第二阶段】：调取整个执行链条的检查点时光树（Time-Travel History）...")
    history = list(app.get_state_history(session_config))
    for idx, snap in enumerate(history):
        c_id = snap.config['configurable']['checkpoint_id']
        next_step = snap.next
        amt = snap.values.get("amount_usd", "N/A")
        status = snap.values.get("audit_status", "N/A")
        print(f"  [{idx}] 检查点 ID: {c_id[:18]}... | 金额: ${amt} | 审计状态: {status:<15} | 下一步: {next_step}")

    # --------------------------------------------------------------------------
    # 阶段 3：时间旅行定位！找到刚刚起草完成、风控尚未开始的那个历史快照
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【第三阶段】：时光倒流！定位到起草之后、风控执行之前的关键检查点...")
    target_snapshot = None
    for snap in history:
        # 下一步正是准备执行 risk_audit 的那个历史瞬间
        if snap.next == ("risk_audit",):
            target_snapshot = snap
            break

    rollback_checkpoint_id = target_snapshot.config['configurable']['checkpoint_id']
    print(f"🎯 选中的时光倒流锚点检查点 ID: {rollback_checkpoint_id}")
    print(f"🎯 该时间点的原始错误状态: 金额=${target_snapshot.values['amount_usd']}")

    # --------------------------------------------------------------------------
    # 阶段 4：状态干预与分叉（Forking a New Timeline）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【第四阶段】：人工介入修改历史状态，开辟一条全新的时间线（Fork）...")
    # 拿到当时那个历史快照的 config
    rollback_config = target_snapshot.config

    # 【核心 API：update_state】
    # 1. 传入历史检查点的 config
    # 2. values: 将金额修正为正确的 $10,000.0
    # 3. as_node="drafter": 告诉系统，本次状态更新伪装为 drafter 节点在当时产生的修正
    # 返回一个全新的 forked_config，代表新时间线的开端！
    forked_config = app.update_state(
        rollback_config,
        values={"amount_usd": 10000.0},  # 正确的金额！
        as_node="drafter"
    )
    print(f"🌱 成功开辟分叉时间线！全新检查点 ID: {forked_config['configurable']['checkpoint_id']}")

    # --------------------------------------------------------------------------
    # 阶段 5：从新时间线恢复执行图（Resume Execution along Forked Branch）
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【第五阶段】：从分叉时间线唤醒执行...")
    # 【入参为什么传 None？】：
    # 因为状态已经在检查点中了，无需外部再提供输入，图引擎会自动从 checkpoint_id 对应现场继续推进！
    final_result = app.invoke(None, config=forked_config)

    print("\n" + "=" * 65)
    print("🎉 【新时间线执行结果（完美逆袭！）】:")
    print(f"  • 最终归档状态 (final_disposition): {final_result['final_disposition']}")
    print(f"  • 最终合同金额 (amount_usd): ${final_result['amount_usd']:,.2f}")
    print(f"  • 最终审计结论 (audit_status): {final_result['audit_status']}")
    print("=" * 65)

    print_graph_mermaid(app, "03_time_travel")
