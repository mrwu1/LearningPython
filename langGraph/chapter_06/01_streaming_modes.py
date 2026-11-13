"""
================================================================================
【LangGraph 阶段六：全场景流式通信与生产网关】第 1 课：复合流式模式（updates / messages / custom）
================================================================================
【核心学习目标】：
1. 掌握 LangGraph 强大的复合流式传输（Composite Streaming）：
   - `stream_mode=["custom", "messages", "updates"]`；
   - 允许单个连接同时接收节点状态增量、大模型打字机 Token，以及业务自定义通知！
2. 掌握 `StreamWriter`（自定义进度事件推送）：
   - 节点签名声明 `writer: StreamWriter`；
   - 在节点计算过程中调用 `writer({"event": "...", "detail": "..."})`；
   - 在图外部实时产生 `custom` 事件，前端可据此渲染进度条或加载骨架屏。
3. 掌握 `messages` 流模式与打字机效果：
   - 捕获 `(AIMessageChunk, metadata)` 元组；
   - 实现前端毫秒级打字机输出，大幅降低用户等待首字的时间感知。
4. 掌握 `updates` 流模式：
   - 捕获每个超步完成时节点提交的状态增量字典。
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

from langchain_core.messages import BaseMessage, HumanMessage, AIMessageChunk
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.types import StreamWriter
from loguru import logger


# ==============================================================================
# 第一步：定义客服状态契约（State Schema）
# ==============================================================================
class CustomerServiceState(TypedDict):
    order_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    courier_status: str  # 骑手实时位置与配送状态 k


# ==============================================================================
# 第二步：定义带有 StreamWriter 的计算节点
# ==============================================================================
# 【StreamWriter 注入规范】：
# 只要节点的参数列表中包含 `writer: StreamWriter`，
# LangGraph 在执行该节点时就会自动注入一个事件发射器。
# 调用 writer(data) 会立刻向外部流式管道推送一个 mode="custom" 的事件！

def intake_analyzer(state: CustomerServiceState, writer: StreamWriter) -> dict:
    """【节点 1：工单分析】：解析用户诉求，并流式通知前端'正在查询工单'。"""
    # 模拟向前端推送实时业务进度
    writer({
        "event": "STEP_START",
        "step": "ORDER_LOOKUP",
        "detail": f"正在向中心数据库检索订单 {state['order_id']} 的元数据..."
    })
    return {"courier_status": "SEARCHING_LOCATION"}


def courier_tracker(state: CustomerServiceState, writer: StreamWriter) -> dict:
    """【节点 2：骑手雷达定位】：模拟查询高德/谷歌 IoT 骑手北斗定位。"""
    writer({
        "event": "STEP_START",
        "step": "GPS_TELEMETRY",
        "detail": "正在握手接入骑手车载 GPS 卫星定位终端..."
    })

    # 模拟卫星定位成功
    eta_report = "骑手【张师傅】距离您约 850 米，正以 25 km/h 速度行驶，预计 6 分钟内送达。"

    writer({
        "event": "STEP_COMPLETE",
        "step": "GPS_TELEMETRY",
        "detail": "GPS 信号已精准锁定，轨迹正常。"
    })
    return {"courier_status": eta_report}


def llm_responder_node(state: CustomerServiceState, writer: StreamWriter) -> dict:
    """
    【节点 3：大模型综合生成】：
    - 先使用 writer 推送'正在组织语言'；
    - 开启 streaming=True，利用 DeepSeek 模型实时生成具有安抚语气的个性化回复。
    """
    writer({
        "event": "STEP_START",
        "step": "LLM_SYNTHESIS",
        "detail": "正在调用 DeepSeek-V3 实时生成富有共情力的客服答复..."
    })

    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0,
        streaming=True  # 👈 必须开启：激活模型逐 Token 流式输出
    )

    prompt = [
        HumanMessage(content=(
            f"你是苍穹外卖的资深智能客服助手。\n"
            f"用户非常着急询问午餐配送进度。\n"
            f"最新调度遥测数据: {state['courier_status']}\n"
            f"请以温暖、礼貌的语气用两句话安抚顾客，并明确告知送达时间。"
        ))
    ]

    # 在复合流模式下，LangGraph 会自动从内部拦截并向外推送 Token 块
    response = llm.invoke(prompt)
    logger.info(f"模型完整生成完毕: {response.content}")
    return {"messages": [response]}


# ==============================================================================
# 第三步：组装图拓扑
# ==============================================================================
def build_streaming_graph():
    builder = StateGraph(CustomerServiceState)

    builder.add_node("intake_analyzer", intake_analyzer)
    builder.add_node("courier_tracker", courier_tracker)
    builder.add_node("llm_responder", llm_responder_node)

    # 串行时序流
    builder.add_edge(START, "intake_analyzer")
    builder.add_edge("intake_analyzer", "courier_tracker")
    builder.add_edge("courier_tracker", "llm_responder")
    builder.add_edge("llm_responder", END)

    return builder.compile()


# ==============================================================================
# 第四步：消费复合流式输出（模拟前端消费）
# ==============================================================================
if __name__ == "__main__":
    app = build_streaming_graph()

    inquiry = {
        "order_id": "SKY-FOOD-9021",
        "messages": [HumanMessage(content="我的午饭到哪里了？都过去半小时了！")],
        "courier_status": ""
    }

    print("\n" + "=" * 65)
    print("🚀 启动复合多通道流式监听 (Simulating Frontend Consumer)")
    print("=" * 65)

    # ==========================================================================
    # 【核心 API：app.stream】
    # stream_mode 传入列表，开启三种通道混合并发流：
    # - "custom": 捕获 StreamWriter 发送的自定义事件
    # - "messages": 捕获大模型逐字生成的 AIMessageChunk
    # - "updates": 捕获每个超步完成时节点返回的状态增量
    # ==========================================================================
    stream_generator = app.stream(
        inquiry,
        stream_mode=["custom", "messages", "updates"]
    )

    token_stream_started = False

    for mode, payload in stream_generator:
        # 1. 业务自定义进度事件（前端用于驱动步骤条/加载指示器）
        if mode == "custom":
            event_type = payload.get("event", "INFO")
            step = payload.get("step", "UNKNOWN")
            detail = payload.get("detail", "")
            print(f"\n[业务进度事件 ⏳] [{event_type}] ({step}): {detail}")

        # 2. 大语言模型逐 Token 打字机流（前端用于打字机效果）
        elif mode == "messages":
            chunk, metadata = payload
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                if not token_stream_started:
                    print("\n[AI 实时回复打字机 🤖]: ", end="", flush=True)
                    token_stream_started = True
                # 原地流式打印单字/词块，不换行
                print(chunk.content, end="", flush=True)

        # 3. 节点超步提交更新（前端或后端用于状态追踪与监控）
        elif mode == "updates":
            node_name = list(payload.keys())[0]
            print(f"\n[节点超步完成 ✅] 节点 '{node_name}' 提交增量: {payload[node_name]}")

    print("\n\n" + "=" * 65)
    print("🎉 流式通信传输顺利完成！")
    print("=" * 65)
