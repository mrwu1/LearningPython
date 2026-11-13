from typing import TypedDict, List, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables.graph import Graph
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END

from utils.model import get_llm

"""lesson_11_crag_langgraph.py                                                                                       

   阶段四 · 4.1 纠错型 RAG (Corrective RAG via LangGraph)                                                               
   核心目标：                                                                                                           
   1. 掌握 CRAG (Corrective RAG) 状态机架构：在检索与生成之间插入“文档质检员”；                                         
   2. 消除检索幻觉与噪声投毒：质检不合格的文档自动剔除；                                                                
   3. 动态条件边路由：当全库无有效知识时，自动分支到兜底/外部补偿节点，绝不硬答胡编。                                   
"""
# state
class CRAGState(TypedDict):
    question:str
    documents:List[str]
    filtered_documents:List[str]
    search_needed:bool
    generation:str

# 质检契约
class GradeDocument(BaseModel):
    """文档相关性安检员裁决契约"""
    binary_score:Literal["yes", "no"] = Field(
        ...,
        description="文档是否包含回答问题所需的有效信息：'yes' 表示相关，'no' 表示完全不相关或噪音",
    )
    reason: str = Field(..., description="判定理由")

# 用户输入问题 -> 向量转化 -> 向量数据库match -> rerank 排序 -> put them into LLM -> ANSWER
# 用户输入问题 -> 向量数据库检索，得到相应的文档列表 -> invoke文档列表，filter出合格的 -> 用户问题+docs put into model

def retrieve_node(state: CRAGState) -> dict:
        """模拟第一步检索节点 (实际生产对接第3课向量库或第8课混合检索)"""
        question = state["question"]
        print(f"\n🔍 [节点 1: retrieve_node] 正在检索知识库... Query='{question}'")

        # 模拟知识库的检索结果 (根据问题特征模拟召回)
        if "深圳" in question or "酒店" in question:
            # 正常召回相关制度
            retrieved = [
                "【集团差旅制度】超一线城市（北上广深）初级员工每日酒店住宿标准上限为450元。",
                "【发票粘贴规范】发票须按时间顺序平整粘贴于A4纸上，不可折叠覆盖。",  # 混入的无关噪声！
            ]
        else:
            # 模拟检索失真：用户问商业保险，知识库由于缺失，错误召回了不相干的办公用品规定
            retrieved = [
                "【办公用品领用办法】员工申请键盘、鼠标等办公外设，需在OA发起申领流程并经主管审批。",
                "【公司前台快递规范】私人快递请于下班后至前台货架自取，前台不承担保管责任。",
            ]

        return {"documents": retrieved}

def grade_documents_node(state: CRAGState) ->dict:
    """拿到向量检索结果，进行再次评估，过滤出所需的文档"""
    llm_width_structured = get_llm().with_structured_output(schema=GradeDocument,method="function_calling")
    documents = state["documents"]
    question = state["question"]
    system_prompt=(
        "你是一位极其严谨的 RAG 知识检索质检员。\n"
        "你的任务是评估给定的参考文档是否与用户提问相关，且能为回答问题提供有效信息。\n"
        "如果文档相关，给出 'yes'；如果是无关噪音、前言不搭后语或无法支撑问题，坚决给出 'no'。"
    )
    valid_docs=[]
    for idx,document in enumerate(documents,1):
        grade_res: GradeDocument = llm_width_structured.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"用户提问：{question}\n\n【待审查文档】：{document}"),
            ]
        )
        if grade_res.binary_score == "yes":
            print(f"   ✅ [文档 {idx} 通过质检]: {grade_res.reason}")
            valid_docs.append(document)
        else:
            print(f"   ❌ [文档 {idx} 判定为噪音/无关，剔除]: {grade_res.reason}")
    # 触发补偿机制
    search_needed = len(valid_docs) == 0
    return {
        "filtered_documents": valid_docs,
        "search_needed":search_needed
    }

def fall_back_node(state: CRAGState) -> dict:
    """补偿兜底节点 (当本地知识库全军覆没时触发，模拟外网搜索或应急知识库)"""
    question = state["question"]
    print(
        f"🚨 [节点 3: fallback_node] 本地知识库无有效信息，已触发补偿降级通道！Query='{question}'"
    )
    # 模拟外部搜索引擎或人力补充规章
    external_docs = [
        "【集团HR最新补充公告(外网同步)】全员入职即购买补充商业医疗险及意外险，理赔流程请登录保司APP自主申报。"
    ]
    return {"filtered_documents": external_docs}

def generate_node(state: CRAGState) -> dict:
    """生成节点：基于经过质检的纯净文档，生成最终回答"""
    question = state["question"]
    filtered_documents = state["filtered_documents"]
    llm = get_llm()
    context = "\n\n".join(filtered_documents)
    system_prompt=(
        "你是一位企业合规答疑助手。请严格仅依据以下参考文档回答用户问题。\n"
        "【参考文档】：\n"
        f"{context}\n\n"
        "要求：陈述事实，逻辑严谨，严禁凭空脑补。"
    )
    res =llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"用户提问：{question}"),
    ])
    return {
        "generation":res.content,
    }
 # ================== 4. 条件路由决策edge ==================
def condition_edge(state: CRAGState) -> str:
    """条件边：根据质检结果，分流至补偿节点或直接生成"""
    search_needed = state["search_needed"]
    if search_needed is True:
         return "fallback"
    return "generate"

def build_crag_graph():
    builder = StateGraph(CRAGState)
    builder.add_node("retrieve",retrieve_node)
    builder.add_node("fallback",fall_back_node)
    builder.add_node("generate",generate_node)
    builder.add_node("grade_documents",grade_documents_node)

    builder.add_edge(START,"retrieve")
    builder.add_edge("retrieve","grade_documents")
    builder.add_edge("fallback","generate")
    builder.add_conditional_edges(
        "grade_documents",
        condition_edge,
        path_map={
            "fallback":"fallback",
            "generate":"generate"
        }
    )
    builder.add_edge("generate",END)
    return builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":

    config={
        "configurable":{
            "thread_id":"SESSION_01"
        }
    }

    app = build_crag_graph()

    print("=" * 80)
    print("🚀 测试用例 1：正常场景（召回包含 1 篇相关制度 + 1 篇无关贴票噪声）")
    # 预期：噪音被剔除，相关文档保留，直接走 generate_node
    q1 = "出差去深圳，初级员工酒店一晚最高能报销多少钱？"
    res1 = app.invoke(
        {
            "question": q1,
            "documents": [],
            "filtered_documents": [],
            "search_needed": False,
            "generation": "",
        },config=config
    )
    print(f"\n💡 [最终回答]:\n{res1['generation']}")

    print("\n" + "=" * 80)
    print("🚀 测试用例 2：异常场景（知识库缺失，召回的全部是办公用品和快递无关文档）")
    config1 = {
        "configurable": {
            "thread_id": "SESSION_02"
        }
    }
    # 预期：全部文档被质检员判为 'no'，触发 fallback_node 兜底，绝不产生胡说八道！
    q2 = "公司给员工买商业补充医疗保险和意外险吗？怎么理赔？"
    res2 = app.invoke(
        {
            "question": q2,
            "documents": [],
            "filtered_documents": [],
            "search_needed": False,
            "generation": "",
        },config=config1
    )
    print(f"\n💡 [最终回答]:\n{res2['generation']}")

