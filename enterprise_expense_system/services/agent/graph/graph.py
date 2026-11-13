from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from schemas.state import ExpenseAuditState
from services.agent.nodes.archive_node import archive_node
from services.agent.nodes.check_invoice_policy_node import check_invoice_policy_node
from services.agent.nodes.compensate_node import compensate_node
from services.agent.nodes.deduct_budget_node import deduct_budget_node
from services.agent.nodes.execute_bank_transfer_node import execute_bank_transfer_node
from services.agent.nodes.human_approval_node import human_approval_node
from services.agent.nodes.risk_assessment_node import risk_assessment_node
from services.agent.nodes.success_node import success_node
from services.agent.edges.approval_router import approval_router
from services.agent.edges.risk_router import risk_router
from services.agent.edges.payout_router import transfer_router, budget_router
from utils.graph_utils import print_graph_mermaid


def build_graph():
    builder = StateGraph(ExpenseAuditState)

    # 注册 nodes
    builder.add_node("check_invoice_policy", check_invoice_policy_node)
    builder.add_node("risk_assessment", risk_assessment_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("execute_bank_transfer", execute_bank_transfer_node)
    builder.add_node("deduct_budget", deduct_budget_node)
    builder.add_node("compensate", compensate_node)
    builder.add_node("archive", archive_node)
    builder.add_node("success", success_node)

    # 绘制 graph
    builder.add_edge(START, "check_invoice_policy")
    builder.add_edge("check_invoice_policy", "risk_assessment")

    builder.add_conditional_edges(
        "risk_assessment",
        risk_router,
        path_map={
            "payout": "deduct_budget",
            "back_archive": "archive",
            "human_approval": "human_approval"
        }
    )
    builder.add_conditional_edges(
        "human_approval",
        approval_router,
        path_map={
            "payout": "deduct_budget",
            "rejected_archive": "archive"
        }
    )
    # 修复：预算扣减后必须经过条件路由判断，严禁预算不足时强行打款！
    builder.add_conditional_edges(
        "deduct_budget",
        budget_router,
        path_map={
            "transfer": "execute_bank_transfer",
            "budget_failed_archive": "archive"
        }
    )
    builder.add_conditional_edges(
        "execute_bank_transfer",
        transfer_router,
        path_map={
            "failure_saga": "compensate",
            "success": "success"
        }
    )

    builder.add_edge("success", END)
    builder.add_edge("compensate", END)
    builder.add_edge("archive", END)

    # 暂时采用内存级别的 checkpointer, 后转为 postgresql
    return builder.compile(checkpointer=InMemorySaver())

# 进程级全局单例：保证所有 HTTP 请求共享同一个 Checkpointer 状态存储
expense_graph = build_graph()
# if __name__ == "__main__":
#     app = build_graph()
#     print_graph_mermaid(app,"app")


