"""
================================================================================
【LangGraph 阶段四：持久化与双层记忆底座】第 4 课：跨会话长期记忆（BaseStore & InMemoryStore）
================================================================================
【核心学习目标】：
1. 彻底搞清“短期会话记忆”与“跨会话长期记忆”的区别：
   - 短期记忆（Checkpointer）：生命周期严格绑定单次会话 `thread_id`，换了会话 ID 记忆就归零。
   - 长期记忆（Store）：生命周期超越会话，按 `(namespace, key)` 树形存储，跨越所有 thread_id 共享！
2. 掌握节点中通过依赖注入获取 Store：
   - 节点签名：`def agent_node(state, config, *, store: BaseStore)`
   - LangGraph 在执行时会自动将编译时注入的 `store` 传入节点。
3. 掌握 Store 核心操作：
   - 写入：`store.put(namespace, key, value_dict)`
   - 读取：`item = store.get(namespace, key)`，通过 `item.value` 获取实际字典。
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

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from loguru import logger


# ==============================================================================
# 第一步：定义单轮会话状态（State Schema）
# ==============================================================================
class BaristaState(TypedDict):
    # 只保存当前会话里的消息
    messages: Annotated[list[BaseMessage], add_messages]


# ==============================================================================
# 第二步：模型获取
# ==============================================================================
def get_llm():
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0
    )


# ==============================================================================
# 第三步：注入长期记忆 Store 的认知计算节点
# ==============================================================================
# 【节点依赖注入 Store 规范】：
# 签名必须使用关键字参数：`*, store: BaseStore`
# 这样 LangGraph 在运行时会自动把图挂载的 Store 实例注入进来！
def barista_agent_node(state: BaristaState, config: RunnableConfig, *, store: BaseStore):
    """
    【咖啡师认知节点】：
    1. 从 config 中提取当前下单用户的唯一 ID（跨线程持久身份）；
    2. 从 Store 中根据命名空间 ("user", user_id, "profiles") 检索该用户的长期偏好；
    3. 将长期记忆拼接为 SystemMessage 注入大模型上下文；
    4. 识别并提取用户对话中透露的最新持久偏好，写回 Store 永久保存。
    """
    # 1. 从运行时配置中提取跨会话的用户真实身份 user_id
    user_id = config.get("configurable", {}).get("user_id", "anonymous")
    user_namespace = ("user", user_id, "profiles")

    # 2. 【核心修复】：从长期记忆 Store 中读取该用户的历史画像
    # 注意：长期记忆保存在 store 中，而非 state 中！
    store_item = store.get(user_namespace, "preferences")
    memory_context = ""
    if store_item:
        user_preferences = store_item.value
        memory_context = f"【系统检索到的用户长期画像与偏好】：{user_preferences}"
        logger.info(f"🔎 [Store 命中] 提取到用户 [{user_id}] 的长期画像: {user_preferences}")
    else:
        logger.info(f"🔎 [Store 未命中] 用户 [{user_id}] 尚无历史偏好记录。")

    # 3. 构造包含长期记忆的系统提示词
    system_instruction = (
        "你是一家高端精品咖啡店的专业咖啡师助手。\n"
        f"{memory_context}\n"
        "如果上面有用户的忌口和口味画像，请在为用户点单时主动关怀并应用这些偏好。"
    )

    llm = get_llm()
    messages_to_send = [SystemMessage(content=system_instruction)] + state["messages"]
    response = llm.invoke(messages_to_send)
    logger.info(f"☕ 咖啡师回复: {response.content}")

    # 4. 从用户最新消息中提炼持久偏好，写回长期 Store
    latest_user_msg = state["messages"][-1].content
    if "lactose intolerant" in latest_user_msg.lower() or "乳糖不耐" in latest_user_msg or "燕麦奶" in latest_user_msg.lower():
        extracted_pref = {
            "milk_choice": "燕麦奶 (Oat Milk)",
            "flavor": "香草糖浆 (Vanilla Syrup)",
            "allergies": ["乳糖不耐受 (Lactose Intolerant)"],
        }
        # 【核心 API：store.put】
        # 将结构化画像写入长期存储树中（跨线程共享）
        store.put(user_namespace, "preferences", extracted_pref)
        logger.info(f"💾 [Store 写入] 成功将偏好持久化至长期记忆 Store 中 (用户: {user_id})！")

    return {"messages": [response]}


# ==============================================================================
# 第四步：组装挂载双层记忆的图（Dual-Memory Graph）
# ==============================================================================
def build_dual_memory_graph(checkpointer: MemorySaver, store: BaseStore):
    builder = StateGraph(BaristaState)
    builder.add_node("barista", barista_agent_node)

    builder.add_edge(START, "barista")
    builder.add_edge("barista", END)

    # 【核心编译配置】：同时传入短期 checkpointer 和长期 store！
    return builder.compile(checkpointer=checkpointer, store=store)


# ==============================================================================
# 第五步：跨会话验证长期记忆（Cross-Session Verification）
# ==============================================================================
if __name__ == "__main__":
    # 实例化双层记忆引擎
    checkpointer = MemorySaver()  # 短期会话记忆
    store = InMemoryStore()       # 长期跨会话记忆

    app = build_dual_memory_graph(checkpointer, store)
    target_user = "user_charlie_77"

    # --------------------------------------------------------------------------
    # 第一天（Day 1）：用户在会话 1 中点单，并透露了乳糖不耐受的秘密
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【第一天 · 会话 1】：用户透露个人饮食偏好...")
    session_1_config = {
        "configurable": {
            "thread_id": "THREAD_SESSION_DAY_1",  # 会话 1
            "user_id": target_user                # 用户 Charlie
        }
    }
    turn_1 = app.invoke({
        "messages": [HumanMessage(content="你好，我叫 Charlie。我有乳糖不耐受，以后我的拿铁请务必帮我换成燕麦奶和香草糖浆！")]
    }, config=session_1_config)
    print(f"🤖 助手响应: {turn_1['messages'][-1].content}")

    # --------------------------------------------------------------------------
    # 第二天（Day 2）：全新会话 2！短期 checkpointer 历史完全为 0！
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("【第二天 · 会话 2】：全新 thread_id！验证短期记忆归零、长期记忆依然生效！")
    session_2_config = {
        "configurable": {
            "thread_id": "THREAD_SESSION_DAY_2",  # 这是一个全新的会话线程！
            "user_id": target_user                # 但用户依然是 Charlie
        }
    }

    # 验证新线程中短期记忆确实为空
    new_thread_snapshot = app.get_state(session_2_config)
    print(f"🔎 验证：会话 2 在提问前，短期记忆中的消息条数: {len(new_thread_snapshot.values.get('messages', []))} 条")

    # 用户仅发出一句模糊的简短点单，绝口不提昨天的偏好
    turn_2 = app.invoke(
        {"messages": [HumanMessage(content="帮我来一杯大杯拿铁，谢谢！")]},
        config=session_2_config
    )
    print(f"🤖 助手响应 (见证奇迹：主动应用燕麦奶！):\n{turn_2['messages'][-1].content}")
    print("=" * 65)
