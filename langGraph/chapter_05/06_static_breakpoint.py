"""
================================================================================
【LangGraph 阶段五：高阶流控与人机协同】第 6 课：编译期静态断点（interrupt_before / interrupt_after）
================================================================================
【核心学习目标】：
1. 掌握编译期静态断点（Static Breakpoints）：
   - `builder.compile(checkpointer=memory, interrupt_before=["execute"])`；
   - 在进入指定节点之前，图引擎会强制无条件暂停挂起。
2. 掌握人机审批的经典三步法（Human-in-the-loop）：
   - 第一步：图执行到断点前自动休眠；
   - 第二步：人工审核员通过 `graph.update_state(config, {"approved": True})` 注入审批决策；
   - 第三步：传入 `None` 调用 `graph.invoke(None, config)` 从断点继续推进直到结束。
3. 对比静态断点与动态中断：
   - 静态断点（compile 配置）：适用于“任何情况都要人工卡点审批”的固定节点（如真实扣款、上线发布）；
   - 动态中断（interrupt 函数）：适用于根据运行中业务数据（如金额 > 500）动态决定是否挂起。
================================================================================
"""

import operator
import sys
from pathlib import Path
from typing import Annotated, TypedDict

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph


# ==============================================================================
# 第一步：定义任务审批状态契约（State Schema）
# ==============================================================================
class ApprovalState(TypedDict):
    task: str                                    # 待执行任务名称，例如 "发布到生产环境"
    approved: bool                               # 人工审批标志（True=同意，False=拒绝）
    log: Annotated[list[str], operator.add]      # 操作审计日志列表（operator.add 自动追加）


# ==============================================================================
# 第二步：定义提案与执行节点
# ==============================================================================

def propose(state: ApprovalState) -> dict:
    """【提案节点】：发起高风险操作申请。"""
    print(f"\n---> [Node: propose] 提交操作提案: {state['task']}")
    return {"log": [f"提出高危任务提案: {state['task']}"]}


def execute(state: ApprovalState) -> dict:
    """
    【高风险执行节点】：
    - 在进入本节点前，图会被静态断点拦截！
    - 恢复执行后，核验 approved 标志并执行具体操作。
    """
    print(f"\n---> [Node: execute] 检查审批状态: approved={state['approved']}")
    if state["approved"]:
        print("  🎉 审批通过！正在执行危险操作...")
        return {"log": [f"已成功执行高危任务: {state['task']}"]}
    
    print("  ❌ 审批未通过或被驳回！任务取消。")
    return {"log": ["任务被人工审批驳回。"]}


# ==============================================================================
# 第三步：组装图拓扑并配置静态断点（Static Breakpoint）
# ==============================================================================
builder = StateGraph(ApprovalState)
builder.add_node("propose", propose)
builder.add_node("execute", execute)

builder.add_edge(START, "propose")
builder.add_edge("propose", "execute")
builder.add_edge("execute", END)

memory = MemorySaver()

# ==============================================================================
# 【核心机制】：compile 阶段显式声明 interrupt_before
# 告诉图引擎：在执行到 'execute' 节点【之前】，无条件保存检查点并立即暂停！
# ==============================================================================
graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["execute"]  # 在进入 execute 节点前强制暂停
)


# ==============================================================================
# 第四步：执行、人工修改状态与恢复
# ==============================================================================
if __name__ == "__main__":
    config = {"configurable": {"thread_id": "approval_session_001"}}

    # --------------------------------------------------------------------------
    # 步骤 1：首次执行图（将在 propose 之后、execute 之前暂停）
    # --------------------------------------------------------------------------
    print("\n========== [Step 1] 发起任务，等待静态断点暂停 ==========")
    initial_input = {
        "task": "部署新版本到生产环境集群 (Deploy to Prod)",
        "approved": False,
        "log": []
    }
    result = graph.invoke(initial_input, config=config)

    print("⏸️ [断点暂停] 当前日志记录:", result["log"])
    snapshot = graph.get_state(config)
    print(f"⏸️ 下一个即将执行但已被暂停的节点: {snapshot.next}")

    # --------------------------------------------------------------------------
    # 步骤 2：人工干预审批，通过 update_state 修改全局状态中的 approved 字段
    # --------------------------------------------------------------------------
    print("\n========== [Step 2] 管理员介入，审核并修改状态 ==========")
    # 模拟技术主管在运维后台点击“确认批准”
    graph.update_state(config, {"approved": True})
    updated_snapshot = graph.get_state(config)
    print(f"✅ 人工干预后的审批标志: approved = {updated_snapshot.values['approved']}")

    # --------------------------------------------------------------------------
    # 步骤 3：传入 None 唤醒图，从断点处继续推进
    # --------------------------------------------------------------------------
    print("\n========== [Step 3] 恢复执行 (传入 None 从现场断点继续) ==========")
    # 传入 None 代表无需新输入，直接利用当前检查点的数据继续往下跑 execute 节点
    final = graph.invoke(None, config=config)

    print("\n" + "=" * 65)
    print("🎉 【执行完毕，全流程审计跟踪日志】:")
    for item in final["log"]:
        print(f"  -> {item}")
    print("=" * 65)
