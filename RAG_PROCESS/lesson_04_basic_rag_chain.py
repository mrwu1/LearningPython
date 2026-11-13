from langchain_core.messages import SystemMessage, HumanMessage

from lesson_03_chroma_store import VectorRecord, MiniChromaCollection
from utils.model import get_llm


def format_retrival_context(results:list[tuple[VectorRecord,float,str]]) -> str:
    """将向量数据库召回的 Top K 记录格式化为带编号与来源标签的 XML 上下文块"""
    if not results:
        return "(未检索到任何相关制度条款)"
    blocks=[]
    # {"category": "HOTEL", "status": "active", "year": 2026},
    for rec,sim,_ in results:
        blocks.append(
            f"<doc id='{rec.doc_id}' category='{rec.metadata.get('category')}' similarity='{sim:.4f}'>\n"
            f"{rec.document}\n"
            f"</doc>"
        )
    return "\n\n".join(blocks)

def run_rag_query(
        collection:MiniChromaCollection,
        question:str,
        query_vec:list[float],
        where_filter:dict|None = None,
        k:int=2
):
    """
    端到端 RAG 核心四步流水线：
    1. Retrieve (带过滤检索) -> 2. Format (组装上下文) -> 3. Augment (构造闭卷 Prompt) -> 4. Generate (LLM 生成)
    """
    # 第 1 步：从向量库检索 Top-K 相关条款
    retrieved = collection.similarity_search_with_score(
        query_embedding=query_vec,
        k=k,
        where=where_filter
    )
    # 第 2 步：拼接为结构化上下文字符串
    context_str = format_retrival_context(retrieved)

    # 第3 步：
    system_prompt = """你是一位严谨的企业差旅合规解答助手。                                                          
        请严格遵循以下三条铁律回答用户问题：                                                                                 
        1. 【闭卷铁律】：你只能依据下方 <context> 标签内提供的现行制度条款进行回答和计算，严禁使用任何外部常识或主观推测！   
        2. 【拒答铁律】：如果 <context>                                                                                      
        中的条款没有提及用户询问的事项，必须直接回答：“【知识库未收录】现行差旅制度中未找到相关规定，请咨询财务部”，严禁编造 
        ！                                                                                                                   
        3. 【溯源铁律】：回答中的每一条结论或金额标准，都必须在句末标注对应的文档编号，格式为 [来源: doc_id]。"""

    user_prompt = f"""<context>
        {context_str}
        </context>

        【用户问题】：{question}"""
    # 第 4 步：调用 DeepSeek 生成最终回答
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return response.content
if __name__ == "__main__":
        # 1. 初始化并灌入企业差旅知识库
        kb = MiniChromaCollection(name="expense_rag_kb")
        kb.upsert(
            ids=["POL-HOTEL-SUPER", "POL-HOTEL-OLD", "POL-MEAL-WEEKEND", "POL-TAXI-DAILY"],
            documents=[
                "【2026新版】超一线城市（北京、上海、广州、深圳）初级员工(JUNIOR)酒店住宿报销上限为450元/晚，资深员工(SENIOR)为650元/晚。",
                "【2020废止版】超一线城市初级员工酒店住宿报销上限为300元/晚。",
                "周末加班餐饮报销上限为150元/天，且必须提供OA加班审批单；无加班审批单一律严禁报销。",
                "工作日市内打车交通费每日报销上限为150元。",
            ],
            embeddings=[
                [0.92, 0.02, 0.05, 0.85],
                [0.93, 0.02, 0.05, 0.86],
                [0.05, 0.95, 0.02, 0.80],
                [0.04, 0.03, 0.96, 0.75],
            ],
            metadatas=[
                {"category": "HOTEL", "status": "active"},
                {"category": "HOTEL", "status": "deprecated"},
                {"category": "MEAL", "status": "active"},
                {"category": "TAXI", "status": "active"},
            ],
        )
        # 场景 1：制度内精准核算与溯源（过滤 status='active' 排除 2020 废止版干扰）
        q1 = "我是初级员工(JUNIOR)，去北京出差住了一晚 600 元的酒店，符合规定吗？超标了多少钱？"
        q1_vec = [0.94, 0.01, 0.04, 0.88]
        print("🔍 提问 1:", q1)
        ans1 = run_rag_query(kb, question=q1, query_vec=q1_vec, where_filter={"status": "active"})
        print("🤖 RAG 回答 1:\n", ans1)
        print("=" * 80)

        # 场景 2：知识库盲区测试（验证闭卷拒答铁律，严防大模型动用常识胡编）
        q2 = "我出差坐飞机买了 200 元的机场头等舱休息室服务，可以报销吗？"
        q2_vec = [0.10, 0.10, 0.85, 0.50]
        print("🔍 提问 2 (盲区测试):", q2)
        ans2 = run_rag_query(kb, question=q2, query_vec=q2_vec, where_filter={"status": "active"})
        print("🤖 RAG 回答 2:\n", ans2)