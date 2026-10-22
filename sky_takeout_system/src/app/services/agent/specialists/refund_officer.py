import json
from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from app.schemas.agent_state import SkyTakeoutState
from app.services.agent.tools.payout_tool import execute_refund_payout


async def refund_officer_worker(state: SkyTakeoutState) -> dict:
    """
    Specialist 3: Handles refund complaints.
    - Amounts <= $50: Auto-approved and disbursed immediately via MySQL ledger.
    - Amounts > $50: Freezes execution via dynamic interrupt() for human manager review.
    """
    # 幂等防重入守卫
    if state.get("refund_status") in ["APPROVED", "REJECTED"]:
        return {
            "messages": [AIMessage(content=f"[Refund Officer]: 该订单已完成处理（状态：{state['refund_status']}），无需重复审批。")],
            "next_worker": "FINISH"
        }

    amount = state.get("refund_amount", 0.0)
    order_number = state.get("order_id", "UNKNOWN")

    # 规则 1：<= 50 元小额，极速自动退款打款并写流水！
    if amount <= 50:
        receipt_str = await execute_refund_payout.ainvoke({
            "order_number": order_number,
            "amount": amount,
            "reason": state.get("refund_reason", "Customer complaint")
        })
        receipt = json.loads(receipt_str)
        return {
            "refund_amount": amount,
            "refund_status": "APPROVED",
            "messages": [AIMessage(content=f"小额退款已秒级完成打款，收据凭证：{receipt.get('tx_receipt')}", name="refund_officer")],
            "next_worker": "FINISH"
        }

    # 规则 2：> 50 元大额高危，触发动态断点挂起！
    admin_approval = interrupt({
        "alert": "HIGH_VALUE_REFUND_ALERT",
        "order_number": order_number,
        "amount": amount,
        "reason": state.get("refund_reason", "Cold food complaint")
    })

    # 当外界通过 Command(resume=decision) 唤醒时，代码直接从这里苏醒继续执行！
    if admin_approval.get("decision") == "APPROVED":
        real_amount = admin_approval.get("approved_amount", amount)
        receipt_str = await execute_refund_payout.ainvoke({
            "order_number": order_number,
            "amount": real_amount,
            "reason": state.get("refund_reason", "Cold food complaint")
        })
        receipt = json.loads(receipt_str)
        return {
            "refund_status": "APPROVED",
            "reviewer_notes": admin_approval.get("notes", "Manager approved"),
            "messages": [AIMessage(content=f"店长审批通过，退款成功，财务凭证：{receipt.get('tx_receipt')}", name="refund_officer")],
            "next_worker": "FINISH"
        }
    else:
        return {
            "refund_status": "REJECTED",
            "reviewer_notes": admin_approval.get("notes", "Manager rejected"),
            "messages": [AIMessage(content="经店长核验，您的退款申请已被驳回。", name="refund_officer")],
            "next_worker": "FINISH"
        }
