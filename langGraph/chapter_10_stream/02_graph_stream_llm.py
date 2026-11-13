"""
================================================================================
【LangGraph 阶段十：流式传输核心进阶】第 2 课：基于 dataclass 状态与 messages 模式的大模型流式输出
================================================================================
【核心学习目标】：
1. 掌握使用 Python 原生 `@dataclass` 作为图状态类型（替代 TypedDict）：
   - 支持属性点访问语法（`state.topic` 代替 `state["topic"]`）；
   - 支持定义字段默认初值（如 `joke: str = ""`）。
2. 掌握节点与底层模型流式解耦：
   - 节点内部只需编写最简单直观的 `model.invoke(...)`，无需手动遍历生成器；
   - 外部调用 `graph.stream(..., stream_mode="messages")` 时，LangGraph 会自动拦截节点内部大模型的 Token 块并向外实时推流！
3. 掌握大模型打字机流式消费：
   - 处理 `(AIMessageChunk, metadata)` 流式块，实现字符级平滑打字输出。
================================================================================
"""

import sys
from dataclasses import dataclass
from pathlib import Path

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessageChunk
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from util.model import get_llm


# ==============================================================================
# 第一步：使用 @dataclass 定义状态契约
# ==============================================================================
# 【核心亮点】：
# 除了 TypedDict 和 Pydantic，LangGraph 原生完全支持标准库的 @dataclass！
# 好处：可以像对象一样通过 `state.topic` 取值，且可以定义字段默认缺省值。
@dataclass
class MyState:
    topic: str        # 用户传入的主题
    joke: str = ""    # 生成的笑话，默认初始为空字符串


# 初始化大模型客户端
model = get_llm()


# ==============================================================================
# 第二步：定义计算节点
# ==============================================================================

def refine_topic(state: MyState) -> dict:
    """【节点 1：丰富主题】：扩展原始关键词。"""
    print(f"\n---> [Node: refine_topic] 原始主题: {state.topic}")
    return {"topic": state.topic + " 和可爱的小猫咪"}


def call_model(state: MyState) -> dict:
    """
    【节点 2：调用 LLM 生成笑话】：
    【关键机制】：
    代码内部直接写 `model.invoke(...)` 即可！
    只要外部开启了 stream_mode="messages"，LangGraph 框架层会自动将模型内部的流式 Token 捕获并推送到外部流管道中！
    """
    print(f"---> [Node: call_model] 大模型正在思考关于【{state.topic}】的笑话...")
    model_response = model.invoke(
        [{"role": "user", "content": f"请为主题【{state.topic}】写一个简短幽默、充满反转的笑话。"}]
    )
    return {"joke": model_response.content}


# ==============================================================================
# 第三步：构建并编译图
# ==============================================================================
graph = (
    StateGraph(MyState)
    .add_node(refine_topic)
    .add_node(call_model)
    .add_edge(START, "refine_topic")
    .add_edge("refine_topic", "call_model")
    .add_edge("call_model", END)
    .compile()
)


# ==============================================================================
# 第四步：消费 stream_mode="messages" 逐 Token 打字机流
# ==============================================================================
if __name__ == "__main__":
    initial_input = {"topic": "程序员加班"}

    print("=" * 65)
    print("🌊 启动 stream_mode='messages' 实时监听大模型打字机流式输出")
    print("=" * 65)

    is_first_token = True

    # 外部传入 stream_mode="messages"
    for chunk, metadata in graph.stream(initial_input, stream_mode="messages"):
        # 过滤并打印大模型返回的 AIMessageChunk 文本片段
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            if is_first_token:
                print("\n[AI 实时作答打字机 🤖]: ", end="", flush=True)
                is_first_token = False
            # 实时流式输出单字/词块，不换行
            print(chunk.content, end="", flush=True)

    print("\n\n" + "=" * 65)
    print("🎉 打字机流式传输圆满完成！")
    print("=" * 65)
