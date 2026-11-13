"""
================================================================================
【LangGraph 阶段四：持久化与双层记忆底座】第 5 课：异步长期记忆与运行时上下文（Async Runtime & Store）
================================================================================
【核心学习目标】：
1. 掌握异步编程范式（Asyncio）：
   - 在高并发后端网关中，所有图节点使用 `async def` 编写，支持 `ainvoke`、`astream`；
   - 掌握长期记忆的异步 API：`await store.asearch(namespace)` 与 `await store.aput(...)`。
2. 掌握现代 LangGraph 运行时上下文协议（Runtime & Context）：
   - 在 `ainvoke(..., context={"user_id": "u001"})` 传入请求级外部上下文；
   - 节点直接通过 `runtime.context["user_id"]` 与 `runtime.store` 访问底层存储。
3. 掌握大模型自省与记忆自动沉淀（Memory Extraction）：
   - 对话结束后，利用 LLM 从问答中提取用户的客观偏好/事实（Fact Extraction）；
   - 将结构化事实持久化到命名空间 `("user_memory", user_id)`，实现完全无感的长期个性化记忆。
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
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from util.model import get_llm


# ==============================================================================
# 第一步：定义异步会话状态
# ==============================================================================
class State(TypedDict):
    messages: list  # 存放多轮对话历史列表


# 获取底层模型实例
llm = get_llm()


# ==============================================================================
# 第二步：定义异步认知节点（借助 Runtime 注入 Context 和 Store）
# ==============================================================================
async def agent_node(state: State, runtime: Runtime):
    """
    【异步个性化 Agent 节点】：
    1. 从 runtime.context 中提取外部传入的用户 ID；
    2. 异步检索 Store 中该用户的历史事实记忆（asearch）；
    3. 将历史事实与当前会话消息拼装送入 LLM 进行回复；
    4. 对话完成后，反思提取对话中的用户事实，异步持久化到长期记忆中（aput）。
    """
    # 1. 从运行时上下文提取用户唯一身份标识
    user_id = runtime.context["user_id"]
    namespace = ("user_memory", user_id)
    store = runtime.store

    # 2. 【核心 API：store.asearch】
    # 异步检索该命名空间下的所有记忆项，并拼装成文本提示词
    memories = await store.asearch(namespace)
    memory_text = "\n".join([m.value["fact"] for m in memories]) if memories else "暂无记忆"
    print(f"🔎 [长期记忆检索] 用户 [{user_id}] 命中记忆: {memory_text}")

    # 3. 组装 SystemMessage 并异步调用大模型进行针对性回复
    resp = await llm.ainvoke([SystemMessage(content=f"已知用户长期偏好：{memory_text}")] + state["messages"])

    # 4. 【记忆自动沉淀】：调用 LLM 从本次对话中提取持久性事实
    extract_prompt = """请从以下对话中提炼用户的持久偏好或客观事实（如忌口、习惯、姓名），以 JSON 格式输出，格式必须为: {"fact": "提炼的事实"}。若无实质持久偏好，则 fact 留空。"""
    fact_json = await llm.ainvoke(extract_prompt + f"\n对话记录：{state['messages'] + [resp]}")

    try:
        fact_data = json.loads(fact_json.content)
        fact = fact_data.get("fact", "")
        if fact and fact.strip(): # None、空字符串 ""、0、空列表 [] 等"假值"，条件直接为 False，
            #❌：防止 fact 为 None 时调用 .strip() 抛出 AttributeError。因为 None.strip() 会报错。
            # 异步持久化到长期存储中（跨会话永久生效）
            await store.aput(namespace, "user_fact", {"fact": fact})
            print(f"💾 [长期记忆写入] 成功沉淀用户新偏好: {fact}")
    except Exception as e:
        print(f"⚠️ [记忆提取异常] JSON 解析或提取失败: {e}")

    return {"messages": [resp]}


# ==============================================================================
# 第三步：组装图拓扑与编译
# ==============================================================================
builder = StateGraph(State)
builder.add_node("agent", agent_node)
builder.add_edge(START, "agent")
builder.add_edge("agent", END)

checkpointer = MemorySaver()  # 短期会话存储
store = InMemoryStore()       # 长期跨会话存储

# 编译图：挂载双层存储
graph = builder.compile(checkpointer=checkpointer, store=store)


# ==============================================================================
# 第四步：异步主函数验证跨线程长期记忆
# ==============================================================================
async def main():
    # --------------------------------------------------------------------------
    # 会话 1：用户在线程 t001 告诉 AI 自己的忌口
    # --------------------------------------------------------------------------
    print("\n========== 第一轮会话 (Thread: t001) ==========")
    config = {"configurable": {"thread_id": "t001"}}
    
    # 【核心参数 context】：将外部请求级的元数据（如 user_id）安全穿透传入运行时
    res = await graph.ainvoke(
        {"messages": [HumanMessage("我叫安安，我吃外卖坚决不吃辣")]},
        config=config,
        context={"user_id": "u001"}
    )
    print("🤖 AI回复：", res["messages"][-1].content)

    # --------------------------------------------------------------------------
    # 会话 2：新开线程 t002！短期记忆已被清空，但 user_id 仍然是 u001
    # --------------------------------------------------------------------------
    print("\n========== 第二轮会话 (Thread: t002 - 全新线程) ==========")
    config2 = {"configurable": {"thread_id": "t002"}}
    res2 = await graph.ainvoke(
        {"messages": [HumanMessage("请问我的点餐忌口是什么？")]},
        config=config2,
        context={"user_id": "u001"}
    )
    print("🤖 AI回复：", res2["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
