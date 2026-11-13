import operator
from typing import TypedDict, Literal, Annotated


class ExpenseAuditState(TypedDict):
    invoice: dict #（或直接存字典形式的发票原始数据）
    policy_result:dict #政策核验结论

    # ：综合风控裁决结论（决定图接下来走哪条条件边）
    # ："AUTO_APPROVED"（合规小额自动过）、"FLAGGED_NEED_APPROVAL"（超标待审批）、"REJECTED"（违规直接毙掉）
    risk_verdict:Literal["AUTO_APPROVED","FLAGGED_NEED_APPROVAL","REJECTED"]
    manager_decision:dict #interrupt

    # 财务事务流转控制标志（专职供条件边判断，不污染 final_status）
    budget_deducted: bool  # T1 部门预算是否扣减成功
    bank_transfer_success: bool  # T2 银行打款是否成功
    compensation_stack: list[str]  # Saga LIFO 补偿栈

    # 纯字符串终态: PAID_SUCCESS / REJECTED_ARCHIVED / PAYOUT_FAILED_COMPENSATED
    final_status:str
    audit_trail:Annotated[list[str],operator.add] #审计流水日志
    simulate_bank_failure:bool # 是否模拟银行网关故障