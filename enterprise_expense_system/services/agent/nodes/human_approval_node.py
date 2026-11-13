from langgraph.types import interrupt
from loguru import logger

from schemas.invoice import ManagerDecision
from schemas.state import ExpenseAuditState


# 第二次的会重新从这里启动
# ❌：外部输入不可信
# ❌：审计断裂 - 加日志
def human_approval_node(state: ExpenseAuditState) -> dict:
    logger.info(f"进入人工审核阶段")
    raw_res = interrupt({
        "invoice":state.get("invoice"),
        "policy_result":state.get("policy_result"),
        "risk_verdict":state.get("risk_verdict"),
    })
    # ✅ 唤醒后：用 Pydantic 强校验主管传入的审批数据结构（若字段拼写错误当场报错，绝不静默误判！）
    decision = ManagerDecision.model_validate(raw_res).model_dump()
    logger.info(f"▶️ 人工审批已唤醒: status={decision['status']}, reason={decision['reason']}")
    return {
        "manager_decision":decision,
        "audit_trail":[f"主管人工审批完成: status={decision['status']}, 批注={decision['reason']}"]
    }

