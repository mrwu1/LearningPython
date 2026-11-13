"""
================================================================================
【LangGraph 阶段四：实战进阶】第 1 课：状态检查点（Checkpointer）与多 Schema 架构
================================================================================
【核心学习目标】：
1. 掌握内存检查点（InMemorySaver）：实现会话记忆、断点续传与状态回溯。
2. 理解 thread_id 会话隔离：不同用户的会话通过 thread_id 进行物理级独立持久化。
3. 理解三层 Schema（InputState / OverAllState / OutputState）的工程价值：
   - InputState：入参校验，拦截脏数据；
   - OverAllState：内部全局工作流转底座，存储过程数据；
   - OutputState：输出清洗过滤，对外界只暴露最终需要交付的字段。
4. 掌握 get_state_history 与图的状态恢复（Time-Travel 基础）。
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict

# 自动将项目根目录加入 sys.path，保证无论在哪个工作目录下都能正常导包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from graph_utils import print_graph_mermaid
from util.model import get_llm


# ==============================================================================
# 第一步：定义三层 Schema 状态契约
# ==============================================================================

# 【1. 入参防腐契约（Input Schema）】：
# 规定外部调用方 invoke 时【必须/只能】传入什么字段。
# 如果外部传参结构不对或漏传，在进入图的第一时间就会被拦截，避免进入后续节点产生脏数据。
class InputState(TypedDict):
    topic: str  # 调用方只需要提供创作主题，例如 "莲花"


# 【2. 输出清洗契约（Output Schema）】：
# 规定图执行结束之后，最终返回给外界调用方的字段。
# 内部中间过程生成的诗歌（poem）、笑话（joke）属于草稿，不对外暴露，保护接口的安全与整洁。
class OutputState(TypedDict):
    final_output: str  # 对外仅暴露最终整合后的成果物


# 【3. 内部全局状态（Internal State Schema）】：
# 图运行过程中，所有节点之间共享的完整上下文黑板。
class OverAllState(TypedDict):
    topic: str         # 主题（来自 InputState）
    poem: str          # 节点 1 生成的诗歌（中间状态）
    joke: str          # 节点 2 生成的笑话（中间状态）
    final_output: str  # 节点 3 整合后的最终文本（投射给 OutputState）


# 初始化大语言模型（底层接入 deepseek-chat）
model = get_llm()


# ==============================================================================
# 第二步：定义图计算节点（Nodes）
# ==============================================================================

# 【提示】：入参注解使用 InputState 只是给开发者或 IDE 的类型提示，
# 运行时代码实际接收到的仍然是当前的完整全局状态。
def node_poem(state: InputState) -> dict:
    """
    【诗歌创作节点】：
    - 从 state 中读取用户给定的 topic；
    - 调用 LLM 写一首诗；
    - 返回 {"poem": poem} 增量更新写入全局状态。
    """
    topic = state["topic"]
    print(f"\n---> [Node: node_poem] 正在为主题【{topic}】创作诗歌...")
    poem = model.invoke([
        HumanMessage(f"写一首关于{topic}的七言绝句")
    ]).content
    return {
        "poem": poem
    }


def node_joke(state: InputState) -> dict:
    """
    【笑话创作节点】：
    - 从 state 中读取用户给定的 topic；
    - 调用 LLM 写一个笑话；
    - 返回 {"joke": joke} 增量更新写入全局状态。
    """
    topic = state["topic"]
    print(f"---> [Node: node_joke] 正在为主题【{topic}】编写幽默笑话...")
    joke = model.invoke([
        HumanMessage(f"写一个关于{topic}的简短笑话")
    ]).content
    return {
        "joke": joke
    }


def node_final_output(state: OverAllState) -> OutputState:
    """
    【最终聚合节点】：
    - 同时读取前面两个并发节点生成的 poem 与 joke；
    - 组装成对外输出的最终排版文本 final_output。
    """
    print("\n---> [Node: node_final_output] 正在整合诗歌与笑话为最终成果...")
    topic = state["topic"]
    poem = state["poem"]
    joke = state["joke"]
    final_output = f"【主题】：{topic}\n\n【诗歌精选】：\n{poem}\n\n【笑话一则】：\n{joke}"
    return {
        "final_output": final_output
    }


# ==============================================================================
# 第三步：组装图拓扑（Graph Topology）
# ==============================================================================
# 声明三层 Schema：
# - state_schema: 内部流转的主状态类型
# - input_schema: 外部调用时的入参校验类型
# - output_schema: 对外暴露的返回值类型
builder = StateGraph(
    state_schema=OverAllState,
    input_schema=InputState,
    output_schema=OutputState
)

# 1. 注册三个节点
builder.add_node("node_poem", node_poem)
builder.add_node("node_joke", node_joke)
builder.add_node("node_final_output", node_final_output)

# 2. 并发扇出（Fan-Out）：
# START 同时触发 node_poem 和 node_joke，两者并行生成
builder.add_edge(START, "node_poem")
builder.add_edge(START, "node_joke")

# 3. 屏障汇聚（Fan-In）：
# node_poem 和 node_joke 均完成后，才执行 node_final_output
builder.add_edge("node_poem", "node_final_output")
builder.add_edge("node_joke", "node_final_output")

# 4. 汇聚结束
builder.add_edge("node_final_output", END)


# ==============================================================================
# 第四步：挂载持久化检查点（Checkpointer）与编译
# ==============================================================================
# 【InMemorySaver 核心原理】：
# 1. 它在内存中维护每个超步（Superstep）执行完毕后的完整状态快照（State Snapshot）。
# 2. 具备 ACID 会话隔离：依靠 thread_id 区分不同用户或会话，互不串台。
# 3. 支持断点恢复与历史溯源（get_state_history）。
checkpointer = InMemorySaver()

# 编译图时挂载 checkpointer
graph = builder.compile(checkpointer=checkpointer)

# 打印生成的 Mermaid 图结构
print_graph_mermaid(graph, "checkpointer_01")


# ==============================================================================
# 第五步：运行与状态历史回溯
# ==============================================================================
if __name__ == "__main__":
    # 【必须配置 configurable.thread_id】：
    # 只要图挂载了 checkpointer，执行 invoke/stream 时就必须传入 thread_id！
    config = {
        "configurable": {
            "thread_id": "session_user_001"  # 会话 1 的专属身份标识
        }
    }

    print("\n========== 第一阶段：执行生成工作流 ==========")
    res = graph.invoke({"topic": "莲花"}, config=config)
    print("\n【外部调用方收到的结果（仅展示 final_output）】：")
    print(res["final_output"])

    print("\n" + "=" * 60)
    print("========== 第二阶段：检查点历史查询（State History） ==========")
    # 遍历该 thread_id 下保存的所有历史检查点快照（从最新往最旧排）
    history_checkpoints = list(graph.get_state_history(config=config))
    print(f"总计持久化了 {len(history_checkpoints)} 个检查点快照：\n")
    for idx, snap in enumerate(history_checkpoints):
        print(f"[{idx}] 检查点 ID: {snap.config['configurable'].get('checkpoint_id')}")
        print(f"    当前下一跳节点 (Next): {snap.next}")
        print(f"    已执行节点状态数据: {list(snap.values.keys())}")
        print("-" * 50)
