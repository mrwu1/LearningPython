from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage
from openai import BaseModel
from pydantic import Field

from lesson_03_chroma_store import MiniChromaCollection
from utils.model import get_llm


# core: invoke model 得到执行数据格式的输出，根据输出结果，进行路由的分发

class QueryRouterDecision(BaseModel):
    """智能检索路由和自查询（Self-query）提取契约"""
    datasource:Literal["POLICY_VECTOR_DB", "SQL_LEDGER_DB", "DIRECT_CHAT"] = Field(
        ...,
        description=(
            "路由目标数据源："
            "POLICY_VECTOR_DB(询问差旅报销标准、规章制度、合规上限)；"
            "SQL_LEDGER_DB(查询具体某张发票的审批进度、打款状态或部门剩余预算余额)；"
            "DIRECT_CHAT(日常打招呼或与财务无关的闲聊)"
        )
    )
    category_filter:Literal["HOTEL", "MEAL", "TAXI", "NONE"] = Field(
        default= "NONE",
        description="当路由到 POLICY_VECTOR_DB 时，自动从用户问题中提取差旅类目用于向量库 where过滤；若无法确定或跨多个类目则填 NONE",
    )
    refined_query:str = Field(
        ...,
        description="提炼后的核心检索词（去除口语废话）",
    )
    reason:str = Field(...,description="路由判断理由")

def route_and_extract_query(user_question:str)->QueryRouterDecision:
    """调用 LLM 一次性完成：1. 数据源路由分流  2. Metadata 过滤条件自动提取  3. 检索词提炼"""
    system_prompt="""你是一位企业财务中台的智能检索路由专家。 
    请分析用户的提问意图，决定应该前往哪个数据源查询，并在查询制度库时自动提取消费类目过滤条件（HOTEL/MEAL/TAXI）。
    """
    structured_llm = get_llm().with_structured_output(
        schema=QueryRouterDecision,
        method="function_calling"
    )

    res = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"用户提问：{user_question}"),
        ],
    )
    return res

def dispatch_query(user_question:str,kb:MiniChromaCollection)->None:
    """根据路由决策，自动分发至对应引擎，并自动组装 where 过滤字典！"""
    print(f"\n🗣️ 用户提问: {user_question}")
    decision = route_and_extract_query(user_question)
    print(
        f"🧭 [智能路由决策] 目标库={decision.datasource} | "
        f"自动提取类目={decision.category_filter} | 提炼词='{decision.refined_query}'\n"
        f"   理由: {decision.reason}"
    )
    if decision.datasource == "POLICY_VECTOR_DB":
        # 🌟 核心亮点：自动将大模型提取出的 category_filter 组装为第 3 课向量库的 where 字典！
        auto_where = {"status": "active"}
        if decision.category_filter != "NONE":
            auto_where["category"] = decision.category_filter

        print(f"   👉 正在执行向量库检索，自动注入过滤条件 where={auto_where}")
        # 使用简单特征向量演示检索命中
        hits = kb.similarity_search_with_score([0.9, 0.1, 0.1, 0.8], k=1, where=auto_where)
        if hits:
            rec, sim, _ = hits[0]
            print(f"   ✅ 向量库精准召回: [{rec.doc_id}] {rec.document}")

    elif decision.datasource == "SQL_LEDGER_DB":
        print("   👉 正在路由至 MySQL/账本查询接口 (不查向量库！)：SELECT * FROM t_expense_ledger ...")

    else:
        print("   👉 正在直接调用通用闲聊回复 (跳过所有数据库查询，0 检索开销！)")
if __name__ == "__main__":
        # 初始化第 3 课的知识库
        kb = MiniChromaCollection(name="routed_kb")
        kb.upsert(
            ids=["POL-HOTEL-2026", "POL-HOTEL-2020", "POL-MEAL-2026", "POL-TAXI-2026"],
            documents=[
                "【2026现行】超一线城市初级员工酒店住宿上限为450元/晚。",
                "【2020废止】超一线城市初级员工酒店住宿上限为300元/晚。",
                "【2026现行】周末加班餐饮上限150元/天，须附OA加班审批单。",
                "【2026现行】工作日市内打车每日上限150元。",
            ],
            embeddings=[
                [0.95, 0.02, 0.02, 0.85],
                [0.96, 0.02, 0.02, 0.86],
                [0.90, 0.95, 0.02, 0.80],
                [0.90, 0.02, 0.95, 0.75],
            ],
            metadatas=[
                {"category": "HOTEL", "status": "active"},
                {"category": "HOTEL", "status": "deprecated"},
                {"category": "MEAL", "status": "active"},
                {"category": "TAXI", "status": "active"},
            ],
        )
        # 测试 3 种截然不同的用户提问，观察智能路由与自动 where 组装！
        test_questions = [
            "我去深圳出差住宾馆，一晚最高能报销多少钱？",
            "帮我查一下我的发票 INV-2026-008 打款成功了没有？技术部还剩多少预算？",
            "你好呀，请问你叫什么名字？",
        ]

        for q in test_questions:
            dispatch_query(q, kb)
            print("-" * 80)