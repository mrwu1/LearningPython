"""
================================================================================
【LangGraph 阶段三：三态融合架构】第 1 课：企业级退款仲裁 ReAct 智能体（Tri-State Defense）
================================================================================
【核心学习目标】：
1. 掌握三态架构（Tri-State Architecture）在真实智能体业务中的工业级落地：
   - 入站契约（Inbound）：Pydantic V2 校验用户退款请求；
   - 内部状态（Internal）：TypedDict 存储 ReAct 思考消息链、内部风控分、后厨责任归属判定等私密数据；
   - 出站脱敏（Outbound）：Pydantic V2 仅向用户暴露核退结果与赔付金额，隐去敏感内部决策链。
2. 掌握智能体首轮初始化（Bootstrap）技巧：
   - 外部入参是结构化业务数据（如 order_id, reason），如何在图的第一步将其动态转化为大模型的自然语言 Prompt。
3. 掌握 ReAct 终态判定：当模型不再发起 tool_calls 时，一次性结算并将终态字段写回 State。
================================================================================
"""

import os
import sys
from pathlib import Path
from typing import TypedDict, Annotated

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.constants import START
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from loguru import logger
from pydantic import BaseModel, Field

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一层：入站防腐契约（Inbound Defense Contract - Pydantic V2）
# ==============================================================================
# 严格检验客户端提交的退款表单：订单号格式、退款理由字数、金额合法性
class RefundInboundRequest(BaseModel):
    order_id: str = Field(..., pattern=r"^SKY-\d+$", description="订单号格式必须为 SKY-12345")
    claim_reason: str = Field(..., min_length=3, description="客户申诉理由（至少3个字符）")
    requested_amount: float = Field(..., gt=0, description="申请退款金额必须严格大于0")


# ==============================================================================
# 第二层：内部流转工作状态（Internal Working State - TypedDict）
# ==============================================================================
# 包含大模型 ReAct 历史、内部风控分、后厨异常核查等敏感商业逻辑数据
class RefundInternalState(TypedDict):
    # 继承自外部入参的基础字段
    order_id: str
    claim_reason: str
    requested_amount: float

    # ReAct 消息对话历史（挂载 add_messages 合并器）
    messages: Annotated[list[BaseMessage], add_messages]

    # --- 内部商业敏感字段（绝不回传给客户端，防止用户逆向风控策略） ---
    internal_risk_score: float       # 内部欺诈风险系数（0.0 ~ 1.0）
    kitchen_incident_found: bool     # 是否核实为后厨责任（如打包洒漏、未按备注制作）

    # --- 对外输出的目标准备字段 ---
    refund_status: str               # 审批结论：APPROVED（通过）或 REJECTED（驳回）
    refund_amount: float             # 最终核准退款金额
    customer_reply: str              # 呈现给客户的安抚答复文本


# ==============================================================================
# 第三层：出站脱敏清洗契约（Outbound Sanitized Contract - Pydantic V2）
# ==============================================================================
# 最终交付给客户端的响应体：自动过滤 internal_risk_score 和 kitchen_incident_found 等机密
class RefundCustomerResponse(BaseModel):
    order_id: str
    refund_status: str
    refund_amount: float
    customer_reply: str


# ==============================================================================
# 第四层：领域业务工具（Domain Business Tools）
# ==============================================================================
@tool
def verify_kitchen_packaging_incident(order_id: str) -> str:
    """
    核查商家后厨出餐监控与打包异常日志，确认是否存在洒漏或餐品损坏事故。

    Args:
        order_id: 待核查的外卖订单号
    """
    logger.info(f"🔍 [后厨核查工具] 正在检索订单 {order_id} 的出品监控记录...")
    # 模拟真实微服务查询：确认后厨餐盒未盖严，汤汁洒漏
    return (
        f"订单 {order_id} 异常记录确认：出餐打包员在封装时未扣紧盒盖，"
        "导致配送途中热汤洒漏至保温袋内，责任在商家后厨。"
    )


# ==============================================================================
# 第五层：模型工厂与 ReAct 决策节点
# ==============================================================================
class LLMClientFactory:
    _cached_client: ChatOpenAI | None = None

    @classmethod
    def get_client(cls) -> ChatOpenAI:
        if cls._cached_client is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            cls._cached_client = ChatOpenAI(
                model="deepseek-chat",
                api_key=api_key,
                base_url=base_url,
                temperature=0.0
            )
        return cls._cached_client


def agent_reasoning_node(state: RefundInternalState) -> dict:
    """
    【退款仲裁决策节点】：
    1. 首轮运行初始化：如果是第一步（messages 为空），将 order_id、claim_reason 等拼装成第一条用户消息。
    2. 调用绑定了后厨核查工具的模型。
    3. 如果模型发起 tool_calls -> 进入 ReAct 工具调用分支；
    4. 如果模型做出最终裁决（无 tool_calls）-> 提取结论，同时写入退款状态与核准金额。
    """
    tools = [verify_kitchen_packaging_incident]
    model_with_tools = LLMClientFactory.get_client().bind_tools(tools)

    # 1. 检查对话历史：若为空，说明是第一次进入图，需要 Bootstrap 构造第一条 HumanMessage
    history = state.get("messages", [])
    if not history:
        oid = state["order_id"]
        reason = state["claim_reason"]
        amount = state["requested_amount"]
        prompt = (
            f"客户对订单 {oid} 发起了退款申请。\n"
            f"申诉原因: '{reason}'，申请退款金额: ${amount:.2f}。\n"
            "请调用后厨核查工具调查是否有商家失误记录，并做出公正的退款仲裁裁决。"
        )
        history = [HumanMessage(content=prompt)]

    # 2. 推理运算
    response = model_with_tools.invoke(history)
    logger.info(f"🧠 [Agent 决策] 模型返回: {response}")

    state_updates = {"messages": [response]}

    # 3. 终态判定：如果模型不再请求工具，说明裁决完成，提取终态业务字段
    if not response.tool_calls:
        state_updates.update({
            "internal_risk_score": 0.05,            # 内部欺诈风险分：极低
            "kitchen_incident_found": True,         # 确认商家失误
            "refund_status": "APPROVED",            # 仲裁结果：退款通过
            "refund_amount": state["requested_amount"],  # 全额赔付
            "customer_reply": response.content      # 给客户的最终回复
        })

    return state_updates


# ==============================================================================
# 第六层：组装三态图拓扑
# ==============================================================================
def build_refund_agent_graph():
    tools = [verify_kitchen_packaging_incident]

    # 显式绑定三态：内部工作状态、外部入参模型、外部出参模型
    builder = StateGraph(
        state_schema=RefundInternalState,
        input_schema=RefundInboundRequest,
        output_schema=RefundCustomerResponse
    )

    # 注册节点
    builder.add_node("agent", agent_reasoning_node)
    builder.add_node("tools", ToolNode(tools))

    # 组装 ReAct 环路
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()


# ==============================================================================
# 第七层：端到端执行与验证
# ==============================================================================
if __name__ == "__main__":
    app = build_refund_agent_graph()
    print_graph_mermaid(app, "03_refund_tri_state")

    # 模拟外部客户端发起的入站请求报文
    client_inbound_payload = {
        "order_id": "SKY-9988",
        "claim_reason": "外卖送到时汤汁全部洒在保温袋里了，餐盒盖子松了。",
        "requested_amount": 22.50
    }

    print("\n========== 开始执行退款仲裁智能体 ==========")
    client_response = app.invoke(client_inbound_payload)

    print("\n" + "=" * 65)
    print("【外部客户端最终收到的脱敏出参】:")
    print(f"  • 返回字段清单: {list(client_response.keys())}")
    print(f"  • 订单编号: {client_response['order_id']}")
    print(f"  • 审批结果: {client_response['refund_status']}")
    print(f"  • 核准退款金额: ${client_response['refund_amount']:.2f}")
    print(f"  • 客户答复通知:\n{client_response['customer_reply']}")
    print("=" * 65)
