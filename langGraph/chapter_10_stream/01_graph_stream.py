"""
================================================================================
【LangGraph 阶段十：流式传输核心进阶】第 1 课：updates 与 values 流式模式对比
================================================================================
【核心学习目标】：
1. 掌握 LangGraph 最常用的两种基础流式模式：
   - `stream_mode="updates"`：
     * 增量模式。只产出当前超步（Superstep）刚刚执行完毕的节点所返回的 Partial Update 差异增量；
     * 输出结构形如：`{"node_name": {"field": "new_value"}}`；
     * 适合前端局部精准刷新、状态变化监听或调试特定节点。
   - `stream_mode="values"`：
     * 全量快照模式。每一步执行完毕后，产出当前图的【完整最新状态】（包含初始输入和历史所有字段）；
     * 输出结构形如：`{"topic": "...", "joke": "..."}`；
     * 适合需要掌握当前全局全貌、持久化完整白板的业务场景。
2. 掌握链式调用（Fluent API）图构建：
   - `StateGraph(State).add_node(...).add_edge(...).compile()`。
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.graph import StateGraph, START, END


# ==============================================================================
# 第一步：定义状态契约（State Schema）
# ==============================================================================
class State(TypedDict):
    topic: str  # 创作主题
    joke: str   # 最终笑话内容


# ==============================================================================
# 第二步：定义计算节点
# ==============================================================================

def refine_topic(state: State) -> dict:
    """【节点 1：主题精炼】：将模糊的主题加工得更加具体和生动。"""
    print("\n---> [Node: refine_topic] 正在丰富和扩展主题...")
    return {"topic": state["topic"] + " and cats (冰淇淋与猫咪)"}


def generate_joke(state: State) -> dict:
    """【节点 2：笑话生成】：基于精炼后的主题产出笑话文本。"""
    print("---> [Node: generate_joke] 正在基于新主题产出笑话...")
    return {"joke": f"这是一个关于【{state['topic']}】的趣味小幽默！"}


# ==============================================================================
# 第三步：链式构建图拓扑（Fluent API）
# ==============================================================================
# 现代 Python 风格：直接连续链式调用注册节点与边，最后 compile()
graph = (
    StateGraph(State)
    .add_node(refine_topic)
    .add_node(generate_joke)
    .add_edge(START, "refine_topic")
    .add_edge("refine_topic", "generate_joke")
    .add_edge("generate_joke", END)
    .compile()
)


# ==============================================================================
# 第四步：对比演示两种流式模式
# ==============================================================================
if __name__ == "__main__":
    initial_input = {"topic": "ice cream"}

    # --------------------------------------------------------------------------
    # 模式一：stream_mode="updates" —— 只捕获每个节点的增量更新（Delta）
    # --------------------------------------------------------------------------
    print("=" * 65)
    print("🌊 【模式一：stream_mode='updates'】(增量模式)")
    print("=" * 65)
    # 预期输出：
    # Step 1: {'refine_topic': {'topic': 'ice cream and cats (冰淇淋与猫咪)'}}
    # Step 2: {'generate_joke': {'joke': '这是一个关于【...】的趣味小幽默！'}}
    for chunk in graph.stream(initial_input, stream_mode="updates"):
        print("  [Updates 增量数据]:", chunk)

    # --------------------------------------------------------------------------
    # 模式二：stream_mode="values" —— 观察每步之后图的全局完整状态全貌
    # --------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("🌊 【模式二：stream_mode='values'】(全量快照模式)")
    print("=" * 65)
    # 预期输出：
    # 初始状态全貌 -> refine_topic 执行后全貌 -> generate_joke 执行后全貌
    for chunk in graph.stream(initial_input, stream_mode="values"):
        print("  [Values 全量快照]:", chunk)
    print("=" * 65)
