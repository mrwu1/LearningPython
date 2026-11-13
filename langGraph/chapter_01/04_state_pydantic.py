"""
================================================================================
【LangGraph 阶段一：基础状态机内核】第 4 课：企业级三层契约架构（Pydantic V2 + TypedDict）
================================================================================
【核心学习目标】：
1. 掌握企业级防腐层（Anti-Corruption Layer）设计：
   - 外部入参验证：使用 Pydantic V2 进行强校验（正则、范围、必填）；
   - 内部流转计算：使用 TypedDict 高性能无损流转；
   - 外部出参脱敏：使用 Pydantic V2 自动裁剪过滤内部敏感信息。
2. 掌握 StateGraph 构造参数中的三种契约：
   - `input_schema`: 外部调用 app.invoke(...) 时的入参校验模型。
   - `state_schema`: 图节点之间流转的全局工作状态。
   - `output_schema`: invoke 最终向调用方返回的数据投射模型。
================================================================================
"""

import operator
import sys
from pathlib import Path
from typing import Annotated, TypedDict
from pydantic import BaseModel, Field
from langgraph.constants import START, END
from langgraph.graph import StateGraph

# 自动将项目根目录加入 sys.path，保证工具类导入无误
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_utils import print_graph_mermaid


# ==============================================================================
# 第一层：外部入参契约（Inbound Schema - Pydantic V2）
# ==============================================================================
# 【作用】：严格校验外部客户端传进来的原始请求，拦截脏数据，防止非法参数进入图系统。
class OrderInputRequest(BaseModel):
    # order_id 必须以 "SKY-" 开头，后跟大写英文字母或数字
    order_id: str = Field(..., pattern=r"^SKY-[A-Z0-9]+$", description="企业级规范订单编号")
    # 价格必须严格大于 0
    total_price: float = Field(..., gt=0.0, description="订单金额必须为正数")
    # 商品清单至少包含 1 件物品
    items: list[str] = Field(..., min_length=1, description="订单至少需包含一件商品")


# ==============================================================================
# 第二层：内部流转工作状态（Internal State - TypedDict）
# ==============================================================================
# 【作用】：图节点内部读写的高性能容器，包含业务执行过程中的草稿、中间分值、审计链路等敏感字段。
class OrderInternalState(TypedDict):
    order_id: str
    total_price: float
    items: list[str]
    
    # --- 内部核心计算字段（绝不能泄露给外部前端/调用方） ---
    internal_risk_score: float                   # 专有风控模型评分
    audit_trail: Annotated[list[str], operator.add]  # 节点审计追踪日志（挂载 operator.add 自动追加拼接）
    order_status: str                            # 订单最终流转状态


# ==============================================================================
# 第三层：外部出参契约（Outbound Schema - Pydantic V2）
# ==============================================================================
# 【作用】：对外返回的数据视图投影（View Projection / Data Sanitization）。
# 关键规则：字段名必须与 OrderInternalState 中的对应字段同名！
# 任何在此模型中未声明的内部字段（如 internal_risk_score、audit_trail）都会被自动过滤剔除！
class OrderOutputResponse(BaseModel):
    order_id: str
    total_price: float
    order_status: str
    # 注意：internal_risk_score 和 audit_trail 未在此处声明，因此外部调用方完全看不到它们


# ==============================================================================
# 第四步：定义图计算节点
# ==============================================================================

def risk_assessment_node(state: OrderInternalState) -> dict:
    """【风控评分节点】：计算内部专有风控分，并记录审计日志。"""
    print(f"\n[RiskNode] 正在对订单 {state['order_id']} 进行风控评估...")
    score = 15.0 if state["total_price"] < 100 else 75.0
    return {
        "internal_risk_score": score,
        "audit_trail": [f"[RiskNode] 完成风控计算，评分: {score}"]
    }


def discount_and_finalize_node(state: OrderInternalState) -> dict:
    """【营销折扣与终态节点】：根据风控结果决定是否给予折扣优惠，并标记 CONFIRMED。"""
    discounted = state["total_price"] * 0.9 if state["internal_risk_score"] < 50 else state["total_price"]
    print(f"[FinalizeNode] 折扣后最终价格: ${discounted:.2f}，确认订单完成。")
    return {
        "total_price": discounted,
        "order_status": "CONFIRMED",
        "audit_trail": ["[FinalizeNode] 订单状态已更新为 CONFIRMED"]
    }


# ==============================================================================
# 第五步：组装多模式图（Multi-Schema Graph）
# ==============================================================================
def build_official_multi_schema_graph():
    # 【核心用法】：将三个契约全部传入 StateGraph
    # 1. 第一个位置参数：内部主状态模型 OrderInternalState
    # 2. input_schema: 指定外部入参校验模型 OrderInputRequest
    # 3. output_schema: 指定对外输出清洗模型 OrderOutputResponse
    builder = StateGraph(
        OrderInternalState,
        input_schema=OrderInputRequest,
        output_schema=OrderOutputResponse
    )

    builder.add_node("risk_assessment", risk_assessment_node)
    builder.add_node("finalize", discount_and_finalize_node)

    builder.add_edge(START, "risk_assessment")
    builder.add_edge("risk_assessment", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


# ==============================================================================
# 第六步：测试与验证
# ==============================================================================
if __name__ == "__main__":
    app = build_official_multi_schema_graph()

    # 模拟外部客户端发送的请求数据
    client_payload = {
        "order_id": "SKY-VIP999",
        "total_price": 88.0,
        "items": ["Singapore Laksa"]
    }

    print("\n========== 开始执行多模式契约图 ==========")
    final_response = app.invoke(client_payload)

    print("\n" + "=" * 60)
    print("【外部客户端最终收到的响应数据（已自动脱敏）】:")
    print(f"  返回对象类型: {type(final_response)}")
    print(f"  返回数据内容: {final_response}")
    print("=" * 60)
    print("【重点观察】：")
    print("虽然内部节点计算了 internal_risk_score 和 audit_trail，")
    print("但因为 output_schema 中没有声明它们，最终输出干净整洁，商业机密与日志未泄露！")
    
    print_graph_mermaid(app, "04")
