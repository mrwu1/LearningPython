import asyncio
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.runtime import Runtime
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from util.model import get_llm


# input schema 入参校验
class GraphInputSchema(BaseModel):
    user_query: str = Field(min_length=1, max_length=300)

# output schema 出参校验
class GraphOutputSchema(BaseModel):
    ai_reply: str
    memory_stored: bool

# 图内部完整State
class State(TypedDict):
    user_query: str
    messages: list
    memory_text: str
    ai_reply: str
    memory_stored: bool


llm = get_llm()

async def entry_mapping(state: State, runtime: Runtime):
    # 图入参已经由 input_schema 校验并写入 state
    user_query = state["user_query"]
    return {
        "messages": [HumanMessage(user_query)]
    }

async def load_memory(state: State, runtime: Runtime):
    store = runtime.store
    user_id = runtime.context["user_id"]
    namespace = ("user_memory", user_id)
    memories = await store.asearch(namespace)
    memory_text = "\n".join([m.value["fact"] for m in memories]) if memories else "暂无用户记忆"
    return {"memory_text": memory_text}

async def agent_chat(state: State, runtime: Runtime):
    resp = await llm.ainvoke([SystemMessage(content=f"用户记忆：{state['memory_text']}")] + state["messages"])
    return {"messages": [resp], "ai_reply": resp.content}

async def extract_save_memory(state: State, runtime: Runtime):
    store = runtime.store
    user_id = runtime.context["user_id"]
    namespace = ("user_memory", user_id)
    full_conversation = state["messages"]
    # extract_prompt = """提取用户事实，输出{"fact":""}，对话：{conv}"""
    # fact_resp = await llm.ainvoke(extract_prompt.format(conv=full_conversation))
    extract_prompt = f"""提取用户事实，输出{{"fact":""}}，对话：{full_conversation}"""
    fact_resp = await llm.ainvoke(extract_prompt)
    import json
    stored = False
    try:
        fact_data = json.loads(fact_resp.content)
        fact = fact_data.get("fact", "").strip()
        if fact:
            await store.aput(namespace, "user_fact", {"fact": fact})
            stored = True
    except Exception:
        pass
    return {"memory_stored": stored}


builder = StateGraph(
    State,
    input_schema=GraphInputSchema,
    output_schema=GraphOutputSchema,
    output_keys=["ai_reply", "memory_stored"] # 挑选输出字段，交给output_schema校验
)
builder.add_node("entry_mapping", entry_mapping)
builder.add_node("load_memory", load_memory)
builder.add_node("agent_chat", agent_chat)
builder.add_node("extract_save_memory", extract_save_memory)

builder.add_edge(START, "entry_mapping")
builder.add_edge("entry_mapping", "load_memory")
builder.add_edge("load_memory", "agent_chat")
builder.add_edge("agent_chat", "extract_save_memory")
builder.add_edge("extract_save_memory", END)

# checkpointer = MemorySaver()
# store = InMemoryStore()
# graph = builder.compile(checkpointer=checkpointer, store=store)
graph = builder.compile()

async def main():
    config = {"configurable": {"thread_id": "t001"}}
    input_data = {"user_query": "我叫安安，外卖不吃辣"}
    result = await graph.ainvoke(input_data, config=config, context={"user_id":"u001"})
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
