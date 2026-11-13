"""
================================================================================
【LangGraph 阶段四：持久化与双层记忆底座】第 1 课：状态检查点（SqliteSaver）与会话记忆
================================================================================
【核心学习目标】：
1. 掌握真实数据库持久化：使用 `SqliteSaver` 代替纯内存的 `InMemorySaver`。
2. 理解 `thread_id`（线程编号）的工业级定位：
   - 它是 LangGraph 进行多轮会话（Conversational Memory）追踪的核心唯一键；
   - 只要携带相同的 `thread_id`，图在唤醒时会自动从数据库中还原上一轮的所有历史。
3. 深入剖析检查点快照（Checkpoint Snapshot）的内部元数据：
   - `thread_id`: 会话标识；
   - `checkpoint_id`: 单调递增的时序唯一标识（UUIDv7）；
   - `checkpoint_ns`: 命名空间（用于支持子图）；
   - `values`: 还原出的当前全局状态；
   - `next`: 下一个等待执行的节点。
4. 探秘 LangGraph 底层 SQLite 表结构：`checkpoints` 与血缘链路（Lineage Parent）。
================================================================================
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import TypedDict, Annotated

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph


# ==============================================================================
# 第一步：定义会话状态契约（State Schema）
# ==============================================================================
class PersistentChatState(TypedDict):
    # 使用 add_messages 自动追加多轮对话
    messages: Annotated[list[BaseMessage], add_messages]


# ==============================================================================
# 第二步：模型与会话计算节点
# ==============================================================================
def get_llm():
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.0
    )


def conversational_agent_node(state: PersistentChatState) -> dict:
    """
    【会话响应节点】：
    大模型在此节点接收到的 state["messages"]，是经过持久化检查点还原后的【完整历史上下文】！
    """
    llm = get_llm()
    print(f"\n🧠 [Chat Node] 正在根据历史已有的 {len(state['messages'])} 条消息进行连贯思考...")
    response = llm.invoke(state["messages"])
    return {"messages": [response]}


# ==============================================================================
# 第三步：组装图并挂载持久化 Checkpointer
# ==============================================================================
def build_persistent_graph(checkpointer: SqliteSaver):
    builder = StateGraph(PersistentChatState)
    builder.add_node("chat", conversational_agent_node)

    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)

    # 【关键编译参数】：checkpointer
    # 将持久化检查点存储引擎注入图运行时中
    return builder.compile(checkpointer=checkpointer)


# ==============================================================================
# 第四步：多轮对话执行与底层数据库剖析
# ==============================================================================
if __name__ == "__main__":
    # 1. 建立 SQLite 数据库连接：
    # （教学使用内存数据库 :memory:，生产环境可传入本地文件路径 "data.db" 或替换为 PostgresSaver）
    db_connection = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(db_connection)

    app = build_persistent_graph(checkpointer)

    # 2. 【核心隔离键 thread_id】：代表客户 Alex 的唯一对话 ID
    session_config = {
        "configurable": {
            "thread_id": "CUSTOMER_SESSION_99"
        }
    }

    # ==========================================================================
    # 第一轮交互：用户透露个人偏好（名字叫 Alex，爱吃榴莲）
    # ==========================================================================
    print("=" * 65)
    print("【第一轮对话】：用户自我介绍...")
    turn_1_payload = {
        "messages": [HumanMessage(content="你好，我叫 Alex，我最喜欢吃的水果是榴莲。")]
    }
    turn_1_response = app.invoke(turn_1_payload, config=session_config)
    print(f"🤖 助手回复: {turn_1_response['messages'][-1].content}\n")

    # ==========================================================================
    # 探秘检查点快照（Snapshot Inspection）
    # ==========================================================================
    snapshot_after_turn_1 = app.get_state(session_config)
    print("🔎 【底层状态检查点快照拆解】:")
    print(f"  • 会话线程 ID (thread_id): {snapshot_after_turn_1.config['configurable']['thread_id']}")
    print(f"  • 检查点版本号 (checkpoint_id): {snapshot_after_turn_1.config['configurable']['checkpoint_id']}")
    print(f"  • 命名空间 (checkpoint_ns): {repr(snapshot_after_turn_1.config['configurable']['checkpoint_ns'])}")
    print(f"  • 下一跳等待执行节点 (Next): {snapshot_after_turn_1.next}")
    print(f"  • 数据库已持久化的消息条数: {len(snapshot_after_turn_1.values['messages'])} 条")

    # ==========================================================================
    # 第二轮交互：用户追问，完全不提供上下文！
    # ==========================================================================
    print("\n" + "=" * 65)
    print("【第二轮对话】：用户追问（未携带任何前文提示）...")
    turn_2_payload = {
        "messages": [HumanMessage(content="请问我叫什么名字？我最喜欢吃什么水果？")]
    }
    # 传入相同的 session_config (相同的 thread_id)，图引擎会自动从 SQLite 中取出前文！
    turn_2_response = app.invoke(turn_2_payload, config=session_config)
    print(f"🤖 助手回复: {turn_2_response['messages'][-1].content}")

    # ==========================================================================
    # 探秘底层 SQLite 数据库实际创建的物理表结构
    # ==========================================================================
    print("\n" + "=" * 65)
    print("🔎 【SQLite 物理表结构直接查询】:")
    cursor = db_connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("LangGraph 自动初始化的数据表:")
    for table in tables:
        print(f"  -> 表名: {table[0]}")

    cursor.execute("SELECT thread_id, checkpoint_id, parent_checkpoint_id FROM checkpoints;")
    rows = cursor.fetchall()
    print("\n检查点演变历史（单向父子血缘链）：")
    for row in rows:
        print(f"  • Thread: {row[0]} | Checkpoint: {row[1]} | 父节点 Parent: {row[2]}")
    print("=" * 65)
