"""
================================================================================
【LangGraph 阶段五：高阶流控与人机协同】第 1 课：动态中断（interrupt）与人类干预（Command Resume）
================================================================================
【核心学习目标】：
1. 掌握现代人机协同（Human-in-the-Loop, HITL）核心机制：
   - 彻底告别旧版笨拙的静态断点（compile(interrupt_before=...)）；
   - 使用现代动态 API：`langgraph.types.interrupt` 与 `Command(resume=...)`。
2. 理解动态中断的工作机制：
   - 节点在运行到 `human_decision = interrupt({...})` 时，图引擎会自动休眠并挂起（Pause）；
   - 传给 `interrupt()` 的字典会被完整写入检查点，供外部前端管理后台或审批流提取展示；
   - 整个会话持久化存储，等待管理员审批（几分钟甚至几天）。
3. 掌握图的唤醒机制：
   - 管理员审批后，向图发送 `app.invoke(Command(resume=approval_data), config=config)`；
   - 图引擎在原节点内无缝唤醒，`interrupt()` 函数直接返回 `approval_data`，流程继续向下推进！
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict, Literal

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command
from loguru import logger

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一步：定义工单审批状态契约（State Schema）
# ==============================================================================
class RefundState(TypedDict):
    order_id: str           # 订单号
    refund_amount: float    # 申请退款金额
    reason: str             # 退款申诉理由
    approval_status: str    # 审批状态：PENDING_REVIEW / AUTO_APPROVED / APPROVED / REJECTED
    reviewer_notes: str     # 人工审核员填写的审批批注
    payout_status: str      # 财务打款状态：INITIATED / PENDING_REVIEW / PAID_OUT


# ==============================================================================
# 第二步：定义业务节点与动态中断（Dynamic Interrupt）
# ==============================================================================

def intake_request_node(state: RefundState) -> dict:
    """【工单受理节点】：校验退款请求，开启审核流程。"""
    print(f"\n---> [Node: intake] 正在登记退款工单: {state['order_id']} | 申请金额: ${state['refund_amount']:,.2f}")
    return {"payout_status": "PENDING_REVIEW"}


def risk_evaluation_node(state: RefundState) -> dict:
    """
    【风控与人机协同节点】：
    - 若退款金额 <= $50：系统低风险自动极速秒退（AUTO_APPROVED）；
    - 若退款金额 > $50：属于高额赔付，代码在此主动触发【动态中断挂起】！
    """
    amount = state["refund_amount"]
    if amount <= 50.0:
        print(f"---> [Node: risk_evaluation] 金额 <= $50，系统快速通道自动核准。")
        return {
            "approval_status": "AUTO_APPROVED",
            "reviewer_notes": "系统小额快速赔付通道"
        }

    print(f"---> [Node: risk_evaluation] ⚠️ 金额 ${amount:,.2f} 超出自动额度！正在向管理后台发起人工审批挂起...")

    # ==========================================================================
    # 【核心 API：interrupt】
    # 1. 代码执行到这里立刻暂停（Halt）！
    # 2. 传给 interrupt 的字典会存储在数据库中，外部系统可通过 snapshot.tasks 获取；
    # 3. 直到外部调用方发送 Command(resume=...) 时，本行才会恢复执行并将审批结果赋给 human_decision！
    # ==========================================================================
    human_decision = interrupt({
        "alert": "HIGH_VALUE_REFUND_REQUIRES_APPROVAL",
        "order_id": state["order_id"],
        "requested_amount": amount,
        "reason": state["reason"]
    })

    print(f"\n---> [Node: risk_evaluation] 🚀 图已被人类审批唤醒！收到管理员最终裁决: {human_decision}")
    return {
        "approval_status": human_decision.get("decision", "REJECTED"),
        "reviewer_notes": human_decision.get("notes", "无批注"),
        "refund_amount": human_decision.get("approved_amount", amount)
    }


def route_after_review(state: RefundState) -> Literal["execute_payout", END]:
    """【路由决策】：只要通过审核（无论自动还是人工），走向财务打款；否则终止。"""
    if state["approval_status"] in ["AUTO_APPROVED", "APPROVED"]:
        return "execute_payout"
    print(f"=== [Router] 🛑 申请被拒绝（状态: {state['approval_status']}），终止流程，不予打款。")
    return END


def execute_payout_node(state: RefundState) -> dict:
    """【打款节点】：调用第三方银行/支付接口给用户退款。"""
    print(f"\n---> [Node: execute_payout] 💰 财务成功放款: 向订单 {state['order_id']} 支付 ${state['refund_amount']:,.2f}！")
    return {"payout_status": "PAID_OUT"}


# ==============================================================================
# 第三步：组装图拓扑
# ==============================================================================
def build_refund_graph(checkpointer: MemorySaver):
    builder = StateGraph(RefundState)
    builder.add_node("intake", intake_request_node)
    builder.add_node("risk_evaluation", risk_evaluation_node)
    builder.add_node("execute_payout", execute_payout_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "risk_evaluation")
    builder.add_conditional_edges("risk_evaluation", route_after_review)
    builder.add_edge("execute_payout", END)

    # 人机协同必须挂载 checkpointer，否则中断时无法持久化暂停现场！
    return builder.compile(checkpointer=checkpointer)


# ==============================================================================
# 第四步：模拟完整的人机协同生命周期
# ==============================================================================
if __name__ == "__main__":
    checkpointer = MemorySaver()
    app = build_refund_graph(checkpointer)

    # 1. 提交一笔高额退款工单（$320.00）
    initial_ticket = {
        "order_id": "ORD-2026-9901",
        "refund_amount": 320.00,
        "reason": "订购了10份高档牛排，送达严重超时且餐品完全冰冷变质。",
        "approval_status": "PENDING",
        "reviewer_notes": "",
        "payout_status": "INITIATED"
    }
    ticket_config = {"configurable": {"thread_id": "TICKET_SKY_888"}}

    print("=" * 65)
    print("【第一阶段】：提交 $320 高额退款，触发动态挂起...")
    app.invoke(initial_ticket, config=ticket_config)

    # 2. 检查图当前的状态：确认图确实已经处于挂起暂停状态
    snapshot = app.get_state(ticket_config)
    print(f"查看数据源，作为练习：{snapshot}")
    print("\n🔎 【检查点挂起状态核验】:")
    print(f"  • 下一个等待执行的节点 (Next): {snapshot.next}")
    print(f"  • 当前任务是否包含中断 (is_interrupted): {bool(snapshot.tasks and snapshot.tasks[0].interrupts)}")

    # 3. 管理后台从检查点中提取当时 interrupt() 抛出的挂起载荷
    interrupt_info = snapshot.tasks[0].interrupts[0].value
    print("\n📋 【OA 审批流管理后台读取到的待办详情】:")
    print(f"  • 告警类型: {interrupt_info['alert']}")
    print(f"  • 订单编号: {interrupt_info['order_id']}")
    print(f"  • 申请金额: ${interrupt_info['requested_amount']:,.2f}")
    print(f"  • 申请理由: {interrupt_info['reason']}")

    print_graph_mermaid(app, "01_human_interrupt")

    # 4. 模拟人工审核主管在后台点击“审批通过（核减 40 元优惠券，实退 280 元）”
    manager_approval_payload = {
        "decision": "APPROVED",
        "approved_amount": 280.00,
        "notes": "经核实冷链配送超时确实属实，扣除赠送的40元代金券后准予退款280元。"
    }

    print("\n" + "=" * 65)
    print("【第二阶段】：主管在管理端审核完毕，使用 Command(resume=...) 唤醒图...")
    # ==========================================================================
    # 【核心唤醒语法】：Command(resume=...)
    # 只要在 invoke 时传入 Command(resume=审批结果)，图就会在 interrupt 停下的地方精准苏醒！
    # ==========================================================================
    final_state = app.invoke(
        Command(resume=manager_approval_payload),
        config=ticket_config
    )

    print("\n" + "=" * 65)
    print("🎉 【流程全部结束，最终状态输出】:")
    print(f"  • 最终审批状态: {final_state['approval_status']}")
    print(f"  • 最终放款金额: ${final_state['refund_amount']:,.2f}")
    print(f"  • 审核员批注: {final_state['reviewer_notes']}")
    print(f"  • 打款状态: {final_state['payout_status']}")
    print("=" * 65)
