# 我们来构建一个真实的业务：《苍穹外卖·订单客服全场景复合流式响应系统》。
#
# 1.Node1(intake_analyzer)：解析用户问题，使用writer推送“正在解析工单”事件；
# 2.Node2(courier_gps_tracker)：模拟调用三方高德 / 谷歌地图查询骑手经纬度，使用
#   writer 推送“正在定位骑手”事件；
# 3.Node3(llm_responder)：调用 DeepSeek 大模型，开启 streaming = True，实时流式生成自然语言回复给顾客！
import os
from typing import TypedDict, Annotated

from dotenv import find_dotenv, load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.types import StreamWriter
from loguru import logger

load_dotenv(find_dotenv())
from langchain_core.messages import BaseMessage, HumanMessage, AIMessageChunk
from langgraph.graph import add_messages, StateGraph


class CustomerServiceState(TypedDict):
    order_id:str
    messages:Annotated[list[BaseMessage],add_messages]
    courier_status:str

def intake_analyzer(state:CustomerServiceState,writer:StreamWriter):
    writer({
        "event": "STEP_START",
        "step": "ORDER_LOOKUP",
        "detail": f"Retrieving order metadata for {state['order_id']}..."
    })
    return {"courier_status": "SEARCHING_LOCATION"}
def courier_tracker(state: CustomerServiceState, writer: StreamWriter):
    writer({"event": "STEP_START",
            "step": "GPS_TELEMETRY",
            "detail": "Connecting to courier IoT GPS satellitetransponder..."
            })
    # Simulated telemetry result
    eta_report = "Courier 'David' is 850 meters away, traveling at 25 km/h. Estimated delivery in 6 minutes."

    writer({"event": "STEP_COMPLETE", "step": "GPS_TELEMETRY", "detail": "GPS signal acquired successfully."})
    return {"courier_status": eta_report}
def llm_responder_node(state: CustomerServiceState, writer: StreamWriter):
    writer({"event": "STEP_START", "step": "LLM_SYNTHESIS",
            "detail": "Generating empathetic response via DeepSeek-  V3..."})
    llm = ChatOpenAI(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=0.0,
            streaming=True # 👈 Critical: Enables token-by-token streaming from the model
        )
    prompt = [
        HumanMessage(content=(
            f"You are a helpful customer service representative for Sky Takeout.\n"
            f"The customer is asking where their order is.\n"
            f"Telemetry Info: {state['courier_status']}\n"
            f"Please respond politely in 2 concise sentences, assuring the customer."
        ))
    ]
    response = llm.invoke(prompt)
    logger.info(f"[Model]:{response}")
    return {"messages":[response]}

def build_streaming_graph():
    builder = StateGraph(CustomerServiceState)

    builder.add_node("intake_analyzer",intake_analyzer)
    builder.add_node("courier_tracker",courier_tracker)
    builder.add_node("llm_responder",llm_responder_node)

    builder.add_edge(START,"intake_analyzer")
    builder.add_edge("intake_analyzer","courier_tracker")
    builder.add_edge("courier_tracker", "llm_responder")

    builder.add_edge("llm_responder", END)

    return builder.compile()

if __name__ == "__main__":
        app = build_streaming_graph()
        inquiry = {
            "order_id": "SKY-FOOD-9021",
            "messages": [HumanMessage(content="Where is my lunch? It's been 30 minutes!")],
            "courier_status": ""
        }
        print(" 🚀 LIVE STREAMING CONSOLE (Simulating Frontend Consumer)")

        #stream - a generator ⚠️
        stream_generator = app.stream(
            inquiry,
            stream_mode=["custom", "messages", "updates"]
        )
        token_stream_started = False
        for mode,payload in stream_generator:
            # 1. Custom Progress Events (StreamWriter)
            if mode == "custom":
                event_type = payload.get("event", "INFO")
                step = payload.get("step", "UNKNOWN")
                detail = payload.get("detail", "")
                print(f"\n[PROGRESS EVENT] ⏳ [{event_type}] ({step}): {detail}")
            # 2. Real-time LLM Token Chunks (Typewriter Effect)
            elif mode == "messages":
                chunk, metadata = payload
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    if not token_stream_started:
                        print("\n[AI RESPONSE TYPING] 🤖: ", end="", flush=True)
                        token_stream_started = True
                # Print token character by character without newline
                print(chunk.content, end="", flush=True)

            # 3. Node Completion Updates
            elif mode == "updates":
                node_name = list(payload.keys())[0]
                print(f"\n[NODE COMPLETED] ✅ Superstep finished for node: '{node_name}'")