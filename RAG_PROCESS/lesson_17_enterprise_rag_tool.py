"""lesson_17_enterprise_rag_tool.py

    阶段五 · 5.1 封装企业生产级 RAG 审计工具
    职责：
    1. 初始化企业规章非结构化知识库 (混合检索底座)；
    2. 定义机器可读的结构化审计契约 PolicyAuditVerdict；
    3. 将端到端 RAG 检索审计链路封装为标准的 LangChain @tool 函数；
    4. 交付生产环境直接调用的无状态工具接口。
"""
from typing import List, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from lesson_03_chroma_store import MiniChromaCollection
from lesson_08_hybrid_search import SimpleBM25
from utils.model import get_llm


class PolicyAuditVerdict(BaseModel):
    """发票合规审计判决契约 (机器与状态机消费)"""
    is_compliant:bool = Field(
        ...,
        description="申请报销金额是否在合规限额内：True(合规）False(不合规）"
    )
    standard_limit:float= Field(
        ...,
        description="制度规定的上限基准金额（元）；无金额限制则填写0.0"
    )
    excess_amount:float= Field(
        default=0.0,
        description="超标金额(元)；未超标或金额在限额内则严格填 0.0"
    )
    is_hard_violation:bool = Field(
        ...,
        description="是否属于不可人工特批的严重硬违规(如私自升舱、虚假发票、非工作餐)；一般超标填 False",
    )
    policy_clause_id:str = Field(
        ...,
        description="命中的制度条款唯一标识编号"
    )
    audit_reason:str = Field(
        ...,
        description="判决理由：必须引用规章原文、陈述对比结果及处置建议"
    )
# 真实企业差旅与合规制度文档
POLICY_DOCUMENTS = [
        {
            "clause_id": "POL-HOTEL-SUPER",
            "category": "HOTEL",
            "city_tier": "SUPER",
            "text":
            "【第四章·住宿标准】超一线城市（北京、上海、广州、深圳）初级员工每日住宿上限450元，总监级别上限650元。超标20%以内须走OA特批，超过20%超出部分一律由个人承担。",
            "embedding": [0.95, 0.10, 0.05, 0.85],
        },
        {
            "clause_id": "POL-HOTEL-FIRST",
            "category": "HOTEL",
            "city_tier": "FIRST",
            "text":
            "【第四章·住宿标准】新一线及二线省会城市初级员工住宿上限350元，总监级别上限500元。超标须提前申请报备。",
            "embedding": [0.85, 0.10, 0.05, 0.75],
        },
        {
            "clause_id": "POL-MEAL-STANDARD",
            "category": "MEAL",
            "city_tier": "ALL",
            "text":
            "【第五章·餐饮标准】工作日出差餐饮补助为每人每天150元据实报销。严禁将个人娱乐、烟酒消费开具餐饮发票，违者视为严重虚假报销。",
            "embedding": [0.10, 0.95, 0.05, 0.80],
        },
        {
            "clause_id": "POL-TRAFFIC-FLIGHT",
            "category": "TRAFFIC",
            "city_tier": "ALL",
            "text":
            "【第六章·交通出行】员工差旅出行国内段默认经济舱。未经事前审批私自升舱产生的超额费用属于不可报销之硬性违规，公司一律不予报销。",
            "embedding": [0.05, 0.10, 0.95, 0.90],
        },
    ]

class PolicyKnowledgeEngine:
    """企业规章检索引擎 (单例模式)"""
    def __init__(self):
        # 1. 稠密向量库初始化
        self.kb = MiniChromaCollection("enterprise_policy_kb")
        ids = [doc["clause_id"] for doc in POLICY_DOCUMENTS]
        texts = [doc["text"] for doc in POLICY_DOCUMENTS]
        embeddings = [doc["embedding"] for doc in POLICY_DOCUMENTS]
        metadatas=[
            {"category": doc["category"], "city_tier": doc["city_tier"]} for doc in POLICY_DOCUMENTS
        ]
        self.kb.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        # doc_id: str
        # document: str
        # embedding: list[float]
        # metadata: dict[str, Any] = field(default_factory=dict)
        # 2. 稀疏 BM25 检索器初始化
        self.bm25 = SimpleBM25(k1=1.5, b=0.75) #Sparse Retriever
        self.bm25.fit(ids=ids,documents=texts)
    def retrieve(
        self,
        query:str,
        category:str,
        query_vector: List[float]
    ):
        """执行带 Metadata 预过滤的混合检索，返回最相关的条款全文"""
        # Metadata 过滤：按消费类目过滤
        where = {"category": category} if category!="ALL" else {}
        # 稠密检索
        dense_hits = self.kb.similarity_search_with_score(
            query_vector,
            k=2,
            where=where,
        )
        if not dense_hits:
            # 降级：若类目过滤无结果，进行全库稠密检索 - ✅：去除where
            dense_hits = self.kb.similarity_search_with_score(
                query_vector, k=1
            )
        top_record, score, _ = dense_hits[0]
        return top_record.document
 # 实例化底层单例引擎
_ENGINE = PolicyKnowledgeEngine()
# ================== 3. 标准 Agent 工具封装 ==================

@tool
def audit_expense_policy_tool(
        category: Literal["HOTEL", "MEAL", "TRAFFIC"],
        city: str,
        amount: float,
        employee_level: Literal["JUNIOR", "DIRECTOR"] = "JUNIOR",
        is_private_upgrade: bool = False,
) -> PolicyAuditVerdict:
    """企业差旅合规审计 RAG 工具。

            根据员工申报的发票类目、出差城市、申报金额及员工职级，检索知识库规章并输出精准的审计合规结论。
    """
    # 1. 提取用户问题的向量
    # 1. 模拟特征向量提取 (与发票参数映射)
    if category == "HOTEL":
        query_vector = (
            [0.95, 0.10, 0.05, 0.85]
            if city in ["北京", "上海", "广州", "深圳"]
            else [0.85, 0.10, 0.05, 0.75]
        )
    elif category == "MEAL":
        query_vector = [0.10, 0.95, 0.05, 0.80]
    else:
        query_vector = [0.05, 0.10, 0.95, 0.90]
    # 2. 检索相关政策条款 - a retriever
    query_text = f"{city} {employee_level} {category} 报销上限 审批要求"
    context = _ENGINE.retrieve(
        query=query_text,
        category=category,
        query_vector=query_vector,
    )

    # 3. LLM 结构化闭卷推演
    system_prompt = (
        "你是一家企业智能财务中台的合规审计裁判。\n"
        "请严格依据给定的参考制度条款，对员工提交的发票申请进行事实核验与合规判定。\n"
        "判定规则：\n"
        "1. 判定 is_compliant：申报金额是否 <= 规定限额且无违规行为；\n"
        "2. 计算 excess_amount：超标金额 = max(0.0, 申报金额 - 规定限额)；\n"
        "3. 判定 is_hard_violation：若存在私自升舱、非工作餐等触碰底线行为，坚决标为 True；常规超标标为 False；\n"
        "4. 提取 standard_limit 和 policy_clause_id，给出明确 audit_reason。"
    )
    user_prompt = (
        f"【参考制度条款】：\n{context}\n\n"
        f"【待审计发票】：\n"
        f"- 消费类目: {category}\n"
        f"- 出差城市: {city}\n"
        f"- 申报金额: {amount} 元\n"
        f"- 员工职级: {employee_level}\n"
        f"- 是否私自升舱: {is_private_upgrade}\n"
    )
    llm = get_llm()
    evaluator = llm.with_structured_output(
        schema=PolicyAuditVerdict, method="function_calling"
    )

    verdict: PolicyAuditVerdict = evaluator.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return verdict

if __name__ == "__main__":
        print("=" * 80)
        print("🧪 场景 1：初级员工在深圳申报酒店住宿 400 元 (预期: 合规)")
        res1 = audit_expense_policy_tool.invoke(
            {
                "category": "HOTEL",
                "city": "深圳",
    		    "amount": 400.0,
                "employee_level": "JUNIOR",
            }
        )
        logger.info(f"返回结果：: {res1}")
        print(f"判决: 合规={res1.is_compliant} | 限额={res1.standard_limit}元")
        print(f"条款: [{res1.policy_clause_id}] {res1.audit_reason}\n")

        print(
            "🧪 场景 2：初级员工在深圳申报酒店住宿 500 元 (预期: 超标50元，可走特批)"
        )
        res2 = audit_expense_policy_tool.invoke(
            {
                "category": "HOTEL",
                "city": "深圳",
                "amount": 500.0,
                "employee_level": "JUNIOR",
            }
        )
        print(
            f"判决: 合规={res2.is_compliant} | 限额={res2.standard_limit}元 | 超标={res2.excess_amount}元"
        )
        print(f"严重硬违规: {res2.is_hard_violation}")
        print(f"条款: [{res2.policy_clause_id}] {res2.audit_reason}\n")

        print("=" * 80)

        print("🧪 ❌场景 3：私自升商务舱申报 2000 元 (预期: 不合规且属于严重硬违规)")
        res3 = audit_expense_policy_tool.invoke(
            {
                "category": "TRAFFIC",
                "city": "北京",
                "amount": 2000.0,
                "employee_level": "JUNIOR",
                "is_private_upgrade": True,
            }
        )
        print(f"判决: 合规={res3.is_compliant} | 严重硬违规={res3.is_hard_violation}")
        print(f"条款: [{res3.policy_clause_id}] {res3.audit_reason}\n")