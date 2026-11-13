"""
================================================================================
【LangGraph 阶段五：高阶流控与人机协同】第 4 课：多步骤连续动态中断与精准 ID 恢复
================================================================================
【核心学习目标】：
1. 掌握连续多节点中断模式（Multi-Step Sequential Interrupts）：
   - 当工作流中包含多个需要人工填写的节点（如节点 A 要姓名，节点 B 要年龄）；
   - 理解图是如何一步一停、逐步收集用户交互信息的。
2. 掌握 `__interrupt__` 返回载荷结构：
   - 每次中断时，图输出中会包含 `__interrupt__` 列表；
   - 每一个中断项包含 `id`（本次中断全局唯一标识）和 `value`（传给 interrupt 的提示信息）。
3. 掌握中断恢复传参技巧：
   - 使用字典映射 `resume_map[i.id] = value` 精准回复指定的中断请求；
   - 使用 `Command(resume=...)` 将外部输入原路交还给中断点继续向下执行。
================================================================================
"""

import sys
from pathlib import Path
from typing import TypedDict

# 自动加入根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command


# ==============================================================================
# 第一步：定义全局状态契约（State Schema）
# ==============================================================================
class OverAllState(TypedDict):
    username: str  # 用户姓名
    age: int       # 用户年龄


# ==============================================================================
# 第二步：定义包含动态中断的节点
# ==============================================================================

def node_a(state: OverAllState) -> dict:
    """
    【节点 A：收集姓名】：
    - 执行到 interrupt("请输入您的姓名") 时，图会挂起暂停；
    - 等待外部通过 Command(resume=姓名) 唤醒时，将姓名赋值给 username 并写回状态。
    """
    print("\n---> [Node A] 开始执行，触发第 1 个中断：等待输入姓名...")
    username = interrupt("请输入您的姓名")
    print(f"---> [Node A] 收到外部输入姓名: {username}")
    return {
        "username": username
    }


def node_b(state: OverAllState) -> dict:
    """
    【节点 B：收集年龄】：
    - 执行到 interrupt("请输入您的年龄") 时，图再次挂起暂停；
    - 等待外部通过 Command(resume=年龄) 唤醒时，将年龄赋值给 age 并写回状态。
    """
    print("\n---> [Node B] 开始执行，触发第 2 个中断：等待输入年龄...")
    age = interrupt("请输入您的年龄")
    print(f"---> [Node B] 收到外部输入年龄: {age}")
    return {
        "age": age
    }


# ==============================================================================
# 第三步：组装图拓扑并编译
# ==============================================================================
builder = StateGraph(state_schema=OverAllState)
builder.add_node("node_a", node_a)
builder.add_node("node_b", node_b)

# 串行拓扑：START -> node_a (挂起) -> node_b (挂起) -> END
builder.add_edge(START, "node_a")
builder.add_edge("node_a", "node_b")
builder.add_edge("node_b", END)

# 中断特性必须依托检查点存储持久化当前暂停现场
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)


# ==============================================================================
# 第四步：多轮中断交互与恢复执行
# ==============================================================================
if __name__ == "__main__":
    # 配置统一的会话 thread_id，用于维持同一个执行实例
    config = {"configurable": {"thread_id": "session_user_profile_999"}}

    # --------------------------------------------------------------------------
    # 步骤 1：首次触发执行，预期在 node_a 挂起
    # --------------------------------------------------------------------------
    print("\n========== [Step 1] 启动工作流，触发第 1 个中断 ==========")
    interrupt_res = graph.invoke({}, config=config)
    print("【图返回结果（包含挂起信息）】:", interrupt_res)

    # --------------------------------------------------------------------------
    # 步骤 2：从中断信息中提取提示，模拟外部输入，唤醒图推进到下一步
    # --------------------------------------------------------------------------
    print("\n========== [Step 2] 响应第 1 个中断 (姓名)，继续推进 ==========")
    resume_map = {}
    
    # 遍历当前图抛出的所有中断任务（每个中断都有唯一 id 和提示文本 value）
    for i in interrupt_res.get("__interrupt__", []):
        prompt_text = i.value
        user_input = "安安"
        print(f"👉 模拟输入 [{prompt_text}] -> {user_input}")
        resume_map[i.id] = user_input

    # 使用 Command(resume=...) 唤醒并恢复图，图将在 node_a 继续，随后流向 node_b 再次挂起！
    resume_res = graph.invoke(Command(resume=resume_map), config=config)
    print("【图第 2 次返回结果（到达 node_b 再次挂起）】:", resume_res)

    # --------------------------------------------------------------------------
    # 步骤 3：响应第 2 个中断（年龄），唤醒图直至完成
    # --------------------------------------------------------------------------
    print("\n========== [Step 3] 响应第 2 个中断 (年龄)，推进至结束 ==========")
    resume_map_b = {}
    for i in resume_res.get("__interrupt__", []):
        prompt_text = i.value
        user_input = 25
        print(f"👉 模拟输入 [{prompt_text}] -> {user_input}")
        resume_map_b[i.id] = int(user_input)

    final_res = graph.invoke(Command(resume=resume_map_b), config=config)
    print("\n" + "=" * 65)
    print("🎉 【流程全部执行完毕，最终状态】:")
    print(final_res)
    print("=" * 65)
