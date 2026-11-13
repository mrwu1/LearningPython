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
    is_grounded:bool
    is_useful:bool
    retry_count:int

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


class GradeHallucination(BaseModel):
    """门禁 1：事实忠实度审查契约 (Grounding Check)"""

    binary_score: Literal["yes", "no"] = Field(
        ...,
        description="回答是否完全基于参考文档事实：'yes' 表示有据可查、无任何捏造；'no'表示存在凭空脑补或与事实相悖的幻觉",
    )
    reason: str = Field(..., description="判定理由")

class GradeAnswer(BaseModel):
        """门禁 2：回答切题度审查契约 (Relevance Check)"""

        binary_score: Literal["yes", "no"] = Field(
            ...,
            description="回答是否正面解答了用户的提问：'yes' 表示切题有效；'no' 表示答非所问、避重就轻",
        )
        reason: str = Field(..., description="判定理由")

 # 审查节点
def grader_for_generation(state: CRAGState) -> dict:
    """双重反思裁判节点：同时执行忠实度(防幻觉)与有效度(防跑题)核验"""
    question = state["question"]
    docs = state["documents"]
    generation = state["generation"]
    print(f"🧐 [节点 3: grade_generation_node] 启动 Self-RAG 自省双门禁审查...")
    print(f"   候选回答: {generation}...")
    llm = get_llm()
    hallucination_grader = llm.with_structured_output(
            schema=GradeHallucination, method="function_calling"
        )
    answer_grader = llm.with_structured_output(
            schema=GradeAnswer, method="function_calling"
    )
    # 门禁 1：审查事实忠实度
    h_res: GradeHallucination = hallucination_grader.invoke(
        [
            SystemMessage(
                content="你是一位严苛的审计审查员。评估回答中的每一个事实是否在参考文档中有依据。有任何捏造或与文档相悖，坚决判定为'no'。"
    ),
    HumanMessage(
        content=f"【参考文档】：\n{docs}\n\n【待审查回答】：\n{generation}"
    ),
    ]
    )

    is_grounded = h_res.binary_score == "yes"
    if is_grounded:
        print(f"   ✅ [门禁 1 事实核验通过]: {h_res.reason}")
    else:
        print(f"   ❌ [门禁 1 拦截到事实幻觉]: {h_res.reason}")

        # 门禁 2：审查切题有效度
    a_res: GradeAnswer = answer_grader.invoke(
        [
            SystemMessage(
                content="你是一位质检专家。评估回答是否正面、切实回答了用户的提问。答非所问判定为 'no'。"
            ),
            HumanMessage(
                content=f"【用户提问】：\n{question}\n\n【待审查回答】：\n{generation}"
            ),
        ]
    )

    is_useful = a_res.binary_score == "yes"
    if is_useful:
        print(f"   ✅ [门禁 2 切题核验通过]: {a_res.reason}")
    else:
        print(f"   ❌ [门禁 2 拦截到答非所问]: {a_res.reason}")

    return {"is_grounded": is_grounded, "is_useful": is_useful}

def regenerate_strict_node(state: CRAGState) -> dict:
    """自我纠错再生节点 (当被检测出幻觉时，强制实施带惩罚约束的闭卷严格重新生成)"""
    question = state["question"]
    docs = state["documents"]
    retries = state.get("retry_count", 0) + 1
    print(
        f"🛡️ [节点 4: regenerate_strict_node] 触发自省惩罚再生 (第 {retries} 次重试)..."
    )

    context = "\n\n".join(docs)
    # 注入更加严苛的防幻觉铁律 Prompt
    system_prompt = (
        "【极其重要的安全审计警告】：你上一次生成的回答被安全门禁拦截，原因包含未经证实的事实脑补！\n"
        "请再次作答，必须严格遵循【闭卷铁律】：\n"
        "1. 仅限使用以下参考文档中出现过的字句与数字；\n"
        "2. 严禁任何主观推测或发散！\n\n"
        f"【参考文档】：\n{context}"
    )
    llm = get_llm()
    res = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"用户提问：{question}"),
        ]
    )
    return {"generation": res.content, "retry_count": retries}



# ================== 4. 条件路由决策edge ==================
def condition_edge(state: CRAGState) -> str:
    """条件边：根据质检结果，分流至补偿节点或直接生成"""
    search_needed = state["search_needed"]
    if search_needed is True:
         return "fallback"
    return "generate"

def condition_grader_edge(state: CRAGState) -> str:
    """双门禁路由：有幻觉回流重写；无幻觉但跑题可重搜；全通关输出"""
    is_grounded = state["is_grounded"]
    is_useful = state["is_useful"]
    if not is_grounded:
        if state.get("retry_count",0)<2:
            print("🔀 [路由判定] 事实不忠实，触发 -> regenerate_strict_node")
            return "regenerate"
        else:
            print(
                "🔀 [路由判定] 超过最大重试次数，终止重试并降级输出 -> end_node"
            )
            return "end"
    if not is_useful:
        print("🔀 [路由判定] 答非所问，终止或重写 -> end_node")
        return "end"
    print("🔀 [路由判定] 双重门禁全票通过！直接输出 -> end_node")
    return "end"

def build_crag_graph():
    builder = StateGraph(CRAGState)
    builder.add_node("retrieve",retrieve_node)
    builder.add_node("fallback",fall_back_node)
    builder.add_node("generate",generate_node)
    builder.add_node("grade_documents",grade_documents_node)
    builder.add_node("grader_for_generation", grader_for_generation)
    builder.add_node("regenerate", regenerate_strict_node)

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
    builder.add_edge("generate","grader_for_generation")
    builder.add_conditional_edges(
        "grader_for_generation",
        condition_grader_edge,
        path_map={
            "regenerate":"regenerate"
        }
    )
    return builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":

    config={
        "configurable":{
            "thread_id":"SESSION_03"
        }
    }

    app = build_crag_graph()
    print("🚀 测试用例 1：正常提问与生成（事实忠实 + 切题有效）")
    q1 = "总监去深圳出差，每晚酒店报销上限是多少？私自升舱能报吗？"
    res1 = app.invoke(
        {
            "question": q1,
            "documents": [],
            "generation": "",
            "retry_count": 0,
            "is_grounded": False,
            "is_useful": False,
        },config=config
    )
    print(f"\n💡 [最终输出回答]:\n{res1['generation']}")

    print(
        "🚀 测试用例 2：故意模拟注入带幻觉的初始回答，观察 Self-RAG 如何拦截并自动触发闭环重生成"
    )
    # 人工制造一个带有严重造假的回答，看自省门禁如何把它打回
    flawed_state = {
        "question": "总监出差私自升舱产生的超额费用，公司给不给报？",
        "documents": [
            "【集团差旅制度】超一线城市总监级别住宿上限为650元/晚；员工因公超标须提前走OA特批，未经特批私自升舱产生的 超额费用一律不予报销。"
    ],
    "generation": "根据制度，总监出差私自升舱完全允许，公司将予以全额实报实销，且额外赠送机场贵宾厅权益。",  # 故意造假！
    "retry_count": 0,
    "is_grounded": False,
    "is_useful": False,
    }
    # 直接从 grade_generation 节点切入测试自省与纠错再生！
    print(f"注入的造假回答: {flawed_state['generation']}")
    # 模拟图执行或者直接通过 grade_generation_node 检验流转
    test_node_res = grader_for_generation(flawed_state)
    flawed_state.update(test_node_res)
    route_target = condition_grader_edge(flawed_state)

    if route_target == "regenerate":
        regen_res = regenerate_strict_node(flawed_state)
        flawed_state.update(regen_res)
        print(f"\n🛡️ 纠错自省后的新生回答:\n{flawed_state['generation']}")
        # 再次送入审查
        recheck = grader_for_generation(flawed_state)
        print(f"二次质检事实忠实度: {recheck['is_grounded']}")


