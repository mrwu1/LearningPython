import asyncio
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage, SystemMessage

from util.model import get_llm


class State(TypedDict):
    messages: list

llm = get_llm()

async def agent_node(state: State, runtime: Runtime):
    user_id = runtime.context["user_id"]
    namespace = ("user_memory", user_id)
    store = runtime.store
    memories = await store.asearch(namespace)
    memory_text = "\n".join([m.value["fact"] for m in memories]) if memories else "暂无记忆"

    resp = await llm.ainvoke([SystemMessage(content=f"用户记忆：{memory_text}")] + state["messages"])

    # 写入长期记忆
    extract_prompt = """从对话提取用户事实，只返回json {"fact":""}"""
    fact_json = await llm.ainvoke(extract_prompt + f"\n对话：{state['messages'] + [resp]}")
    import json
    try:
        fact_data = json.loads(fact_json.content)
        fact = fact_data["fact"]
        if fact.strip():
            await store.aput(namespace, "user_fact", {"fact": fact})
    except Exception as e:
        print(f"记忆提取异常: {e}")
    return {"messages": [resp]}

builder = StateGraph(State)
builder.add_node("agent", agent_node)
builder.add_edge(START, "agent")
builder.add_edge("agent", END)

checkpointer = MemorySaver()
store = InMemoryStore()

graph = builder.compile(checkpointer=checkpointer, store=store)

async def main():
    config = {"configurable": {"thread_id": "t001"}}
    # context 传给runtime
    res = await graph.ainvoke(
        {"messages": [HumanMessage("我叫安安，外卖不吃辣")]},
        config=config,
        context={"user_id": "u001"}
    )
    print("AI回复：", res["messages"][-1].content)

    # 新开线程测试跨会话长期记忆
    print("\n==== 新开thread，同一个user_id，读取记忆 ====")
    config2 = {"configurable": {"thread_id": "t002"}}
    res2 = await graph.ainvoke(
        {"messages": [HumanMessage("我的点餐忌口是什么？")]},
        config=config2,
        context={"user_id": "u001"}
    )
    print("AI回复：", res2["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
