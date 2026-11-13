from typing import Tuple, List

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from lesson_03_chroma_store import VectorRecord, MiniChromaCollection
from utils.model import get_llm


class DocumentRerankScore(BaseModel):
    """单个候选文档的精排打分契约"""
    score: float = Field(
        ...,
        description="该文档与用户问题的实际契合度评分 (0.0 ~ 100.0 分)，严格考虑逻辑否定、前提条件等细节",
    )
    reason: str = Field(
        ...,
        description="打分理由：指出该条款是正面回答、条件不符还是反向无关",
    )

class CrossEncoderReranker:
    def __init__(self):
        self.llm = get_llm()
        self.structured_evaluator = self.llm.with_structured_output(
            schema=DocumentRerankScore, method="function_calling"
        )

    def score_pair(self,query:str,document:str)->Tuple[float,str]:
        """将 Query 与 Document 拼接送入模型，进行深度全交叉注意力打分"""
        system_prompt = (
            "你是一位极其严苛的企业财务合规审计专家，负责对候选制度文本进行相关性重排打分。\n"
            "打分标准：\n"
            "- 90~100分：完全精准匹配用户的提问意图，前置条件和逻辑结论完全一致；\n"
            "- 60~89分：虽然提及相关主题，但存在前提条件出入；\n"
            "- 0~30分：虽然字面上包含相同词汇，但结论相反（如问'不能报'却给出'可以报'）或完全无关。"
        )
        user_prompt = f"【用户问题】：{query} \n\n 【待评估候选文档】: {document}\n\n请严格评估该文档能否准确解答用户的问题并打分。"
        res:DocumentRerankScore = self.structured_evaluator.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        return res.score, res.reason

    def rerank(
        self,
        query:str,
        candidates:List[VectorRecord], # 取出来的向量集合
        top_n:int=2
    )-> List[Tuple[VectorRecord, float, str]]:
        """对第一阶段粗排候选集进行全量交叉重排"""
        score_candidates=[]
        for vector in candidates:
            score,reason = self.score_pair(query,vector.document)
            score_candidates.append((vector,score,reason))
        # 按精排打分从高到低排序 score 关键词
        score_candidates.sort(key=lambda m:m[1],reverse=True)
        return score_candidates[:top_n]


if __name__ == "__main__":
    # 1. 模拟第一阶段向量库 (Bi-Encoder 双塔粗排)
    kb = MiniChromaCollection(name="rerank_test_kb")

    # 构造极具迷惑性的对比语料
    doc_ids = ["DOC-PASS-SPECIAL", "DOC-DENY-PRIVATE", "DOC-BENEFIT-VACATION"]
    documents = [
        "【因公特批报销制度】员工出差因公紧急情况并经总监特批，升舱产生的超标差旅费用，公司予以全额报销。",
        "【违规私自超标制度】员工出差因私自升舱产生的超额费用，属于违规行为，公司一律不予报销，由个人全额自理。",
        "【带薪年假与体检福利】员工入职满一年享有5天带薪年假，年度体检费用在定点医院由公司直接统一结算。",
    ]

    # 特征向量模拟：双塔模型极其容易被“出差、特批、升舱、超标、报销”等高频词带偏
    # DOC-PASS-SPECIAL 与提问字面高度重合，粗排余弦相似度被顶到最高！
    simulated_embeddings = [
        [0.96, 0.88, 0.90, 0.85],  # DOC-PASS-SPECIAL (粗排被误判排在最前)
        [0.92, 0.85, 0.86, 0.20],  # DOC-DENY-PRIVATE (正解，但因否定语气在双塔中略低)
        [0.10, 0.05, 0.05, 0.95],  # DOC-BENEFIT-VACATION (无关)
    ]
    kb.upsert(
        ids=doc_ids,
        documents=documents,
        embeddings=simulated_embeddings,
        metadatas=[{"status": "active"}] * 3,
    )

    # 2. 用户发起提问（带有明确逻辑前提：未提前特批、私自升舱、给不给报）    ❓❓❓
    user_query = "员工出差未提前特批，因私自升舱产生的超标费用，公司给不给报销？"
    query_vector = [0.95, 0.87, 0.89, 0.80]

    # 第一阶段：Bi-Encoder 粗排检索
    coarse_hits = kb.similarity_search_with_score(query_vector,3) #[(record, sim, cosine_distance)]
    print("📉 【第一阶段：Bi-Encoder 双塔粗排榜单 (仅看向量相似度)】")
    coarse_candidates: List[VectorRecord] = []
    for rank, (rec, sim, _) in enumerate(coarse_hits, 1):
        print(f"Rank {rank}: [{rec.doc_id}] 相似度={sim:.4f}")
        print(f"   文本: {rec.document}")
        coarse_candidates.append(rec)

    # 第二阶段：Cross-Encoder 深度重排序
    reranker = CrossEncoderReranker()
    fine_results = reranker.rerank(
        query=user_query,
        candidates=coarse_candidates,#[VectorRecord]
        top_n=2
    )
    print("\n🏆 【最终 Rerank 精排终榜 (名次反转，精准去噪)】")
    for rank, (rec, score, reason) in enumerate(fine_results, 1):
        print(f"   Top {rank}: [{rec.doc_id}] 精排得分={score:.1f}")
        print(f"          理由: {reason}")
        print(f"          文本: {rec.document}\n")
