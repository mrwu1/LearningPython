"""
================================================================================
【LangGraph 阶段五：高阶流控与人机协同】第 5 课：工业级输入输出裁剪与校验（input_schema / output_schema）
================================================================================
【核心学习目标】：
1. 掌握三层 Schema 在异步图中的落地与输出白名单：
   - `input_schema=GraphInputSchema`: 使用 Pydantic V2 校验用户提问长度（1-300字）；
   - `output_schema=GraphOutputSchema`: 仅对前端返回 `ai_reply` 与 `memory_stored` 状态；
   - 内部完整的 `State`: 维护 messages、memory_text 等多步运行过程。
2. 理解节点分层流水线（Pipeline）：
   - entry_mapping: 外部入参结构转换为消息；
   - load_memory: 从长期存储（Store）提取用户历史画像；
   - agent_chat: 大模型带上下文生成对话；
   - extract_save_memory: 异步自动提取新事实并沉淀回长期记忆库。
3. 掌握生产级 Store 与 Runtime 联合编译运行。
================================================================================
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing_extensions import TypedDict

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field
from util.model import get_llm


# ==============================================================================
# 第一步：定义输入校验契约（Input Schema - Pydantic V2）
# ==============================================================================
# 限制客户端输入的 query 必须在 1 到 300 个字符之间，拦截空请求或恶意超长 Prompt
class GraphInputSchema(BaseModel):
    user_query: str = Field(..., min_length=1, max_length=300, description="用户提问内容")


# ==============================================================================
# 第二步：定义对外输出契约（Output Schema - Pydantic V2）
# ==============================================================================
# 对前端展示的洁净响应：包含 AI 回复正文，以及本次是否沉淀了新记忆的布尔值
class GraphOutputSchema(BaseModel):
    ai_reply: str
    memory_stored: bool


# ==============================================================================
# 第三步：图内部流转的完整工作状态（Internal State）
# ==============================================================================
class State(TypedDict):
    user_query: str          # 外部入参
    messages: list           # 对话消息链
    memory_text: str         # 从长期记忆库加载的用户画像
    ai_reply: str            # 模型生成的回复
    memory_stored: bool      # 是否成功写入新事实


# 初始化大模型实例
llm = get_llm()


# ==============================================================================
# 第四步：定义各个流水线节点（Pipeline Nodes）
# ==============================================================================

async def entry_mapping(state: State, runtime: Runtime):
    """
    【1. 输入转换节点】：
    入参 user_query 已经被 input_schema 严格校验，这里将其转化为标准的 HumanMessage 消息。
    """
    user_query = state["user_query"]
    print(f"\n---> [Node 1: entry_mapping] 接收到合法输入: '{user_query}'")
    return {
        "messages": [HumanMessage(content=user_query)]
    }


async def load_memory(state: State, runtime: Runtime):
    """
    【2. 记忆读取节点】：
    从异步长期存储（runtime.store）中根据当前用户 ID 检索其历史忌口与喜好。
    """
    store = runtime.store
    user_id = runtime.context.get("user_id", "default_user")
    namespace = ("user_memory", user_id)

    # 异步检索该用户的长期记忆条目 ‼️‼️ ‼️‼️ ‼️‼️ ‼️‼️
    memories = await store.asearch(namespace)
    memory_text = "\n".join([m.value["fact"] for m in memories]) if memories else "暂无用户偏好记录"
    print(f"---> [Node 2: load_memory] 检索用户 [{user_id}] 历史记忆: {memory_text}")
    return {"memory_text": memory_text}


async def agent_chat(state: State, runtime: Runtime):
    """
    【3. 大脑对话节点】：
    注入长期画像，调用大语言模型进行业务响应。
    """
    print("---> [Node 3: agent_chat] 正在结合上下文生成针对性回复...")
    resp = await llm.ainvoke(
        [SystemMessage(content=f"已知用户长期偏好：{state['memory_text']}")] + state["messages"]
    )
    return {
        "messages": [resp],
        "ai_reply": resp.content
    }


async def extract_save_memory(state: State, runtime: Runtime):
    """
    【4. 记忆提炼与保存节点】：
    分析对话内容，提炼出可持久化保存的个人事实（如忌口习惯），写入 Store。
    """
    print("---> [Node 4: extract_save_memory] 分析对话提炼用户画像...")
    store = runtime.store
    user_id = runtime.context.get("user_id", "default_user")
    namespace = ("user_memory", user_id)
    full_conversation = state["messages"]

    extract_prompt = f"""请分析以下对话，提取用户的客观偏好（如忌口、口味），只返回标准 JSON 字符串，格式为: {{"fact": "具体偏好"}}。若无新偏好，则 fact 留空。\n对话：{full_conversation}"""
    fact_resp = await llm.ainvoke(extract_prompt)

    stored = False
    try:
        fact_data = json.loads(fact_resp.content)
        fact = fact_data.get("fact", "").strip()
        if fact:
            # 写入长期记忆‼️‼️ ‼️‼️ ‼️‼️ ‼️‼️
            await store.aput(namespace, "user_fact", {"fact": fact})
            print(f"💾 成功持久化新偏好: {fact}")
            stored = True
    except Exception as e:
        print(f"⚠️ 记忆解析异常: {e}")

    return {"memory_stored": stored}


# ==============================================================================
# 第五步：组装图拓扑与多模式编译
# ==============================================================================
builder = StateGraph(
    State,
    input_schema=GraphInputSchema,
    output_schema=GraphOutputSchema
)

# 注册 4 个串行节点
builder.add_node("entry_mapping", entry_mapping)
builder.add_node("load_memory", load_memory)
builder.add_node("agent_chat", agent_chat)
builder.add_node("extract_save_memory", extract_save_memory)

builder.add_edge(START, "entry_mapping")
builder.add_edge("entry_mapping", "load_memory")
builder.add_edge("load_memory", "agent_chat")
builder.add_edge("agent_chat", "extract_save_memory")
builder.add_edge("extract_save_memory", END)

# 挂载会话存储与长期存储
checkpointer = MemorySaver()
store = InMemoryStore()
graph = builder.compile(checkpointer=checkpointer, store=store)


# ==============================================================================
# 第六步：异步执行与验证
# ==============================================================================
async def main():
    config = {"configurable": {"thread_id": "thread_demo_001"}}
    # 模拟外部合法输入
    input_data = {"user_query": "我叫安安，我点外卖坚决不吃辣，记得帮我备注"}

    print("\n========== 开始执行 Schema 校验与流水线处理 ==========")
    # context 传入用户身份 user_id
    result = await graph.ainvoke(input_data, config=config, context={"user_id": "u001"})

    print("\n" + "=" * 65)
    print("【前端最终收到的响应（严格受限为 output_schema 声明的字段）】:")
    print(f"  • AI 回复内容: {result['ai_reply']}")
    print(f"  • 是否成功保存偏好: {result['memory_stored']}")
    print(f"  • 响应字典的键: {list(result.keys())}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
