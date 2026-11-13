from langchain_core.messages import SystemMessage, HumanMessage

from lesson_03_chroma_store import MiniChromaCollection
from utils.model import get_llm


def generate_hypothetical_doc(query:str):
    """
    HyDE 核心步骤：
    不直接拿用户的短问题去检索，而是先让 LLM 模仿《企业差旅规章制度》的官方书面体裁，
    生成一段“假设性的制度条文”（作为高维特征空间的检索鱼饵）。
    """
    system_prompt = """你是一位企业财务制度撰稿人。
    请针对用户的提问，模仿正式《企业差旅和费用报销管理规范》的官方书面语题材，撰写一段約 60~100 字的假设性规章制度条文。 
    要求：                                                                                                               
    1. 只输出假设的制度条文正文，不要有任何寒暄或解释；                                                                  
    2. 尽可能使用标准的财务与行政合规专业术语（如：因公出差、退改签手续费、不可抗力、审批凭据、据实报销、费用上限等）。
    """

    llm = get_llm()
    res = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"用户提问：{query}"),
    ])
    return str(res.content).strip()

def mock_feature_extractor(text: str) -> list[float]:
        """
        模拟白盒 Embedding 特征提取器 (4维特征空间)：
        维度 0: [口语疑问词特征] (怎么、吗、啥、能不能)
        维度 1: [官方制度体裁特征] (规定、标准、上限、凭据、审批、据实报销)
        维度 2: [机票/退改签业务特征] (机票、航班、退票、改签、行程变更)
        维度 3: [餐饮/住宿业务特征] (酒店、住宿、吃饭、餐饮)
        """
        colloquial_score = sum(1 for w in ["吗", "怎么", "能不能", "？", "啥"] if w in text) * 0.35
        official_score = sum(1 for w in ["规定", "标准", "审批", "凭据", "凭证", "报销", "因公", "上限"] if w in text) * 0.25
        flight_score = sum(1 for w in ["机票", "退票", "改签", "航班", "行程", "手续费"] if w in text) * 0.30
        hotel_meal_score = sum(1 for w in ["酒店", "住宿", "餐饮", "吃饭"] if w in text) * 0.30

        # 保底微小值防止零向量
        return [
            min(colloquial_score + 0.01, 1.0),
            min(official_score + 0.01, 1.0),
            min(flight_score + 0.01, 1.0),
            min(hotel_meal_score + 0.01, 1.0),
        ]
if __name__=="__main__":
    # 1. 初始化知识库（存入官方书面语制度条文）
    kb = MiniChromaCollection(name="hyde_demo_kb")
    docs = [
        "第八条：因公出差行程变更产生的机票退票、改签手续费，须提供部门主管审批凭据及航空公司退票凭证，方可据实报销。",
        "第九条：员工因公出差期间预订酒店住宿后未入住产生的房费损失，无正当审批理由不予报销。",
    ]
    kb.upsert(
        ids=["POL-FLIGHT-REFUND", "POL-HOTEL-NOSHOW"],
        documents=docs,
        embeddings=[mock_feature_extractor(d) for d in docs],
    )
    user_question = "客户突然改期，我的机票退票扣的手续费能报吗？"
    print(f"🗣️ 员工原始口语提问:\n   {user_question}")
    # 方式 A：直接拿口语短问题算向量去搜 (Query-to-Doc)
    raw_query_vec = mock_feature_extractor(user_question)
    res_direct = kb.similarity_search_with_score(raw_query_vec, k=1)[0]
    print("\n" + "=" * 75)
    print(f"❌ 方式 A (直接拿短问题裸搜) | 命中: [{res_direct[0].doc_id}] | 余弦相似度: {res_direct[1]:.4f}")
    print(f"   原因分析: 原始问题带有浓重的[口语疑问特征]，缺少[官方制度体裁词汇]，向量方向存在夹角偏差。")

    # 方式 B：HyDE 先生成“假想制度条文”，再拿假想条文算向量去搜 (Doc-to-Doc)
    hypo_doc = generate_hypothetical_doc(user_question) # 区别：✅✅✅
    print(f"🤖 DeepSeek 生成的【HyDE 假想制度鱼饵】:\n   {hypo_doc}")
    hyde_vec = mock_feature_extractor(hypo_doc)
    res_hyde = kb.similarity_search_with_score(hyde_vec, k=1)[0]
    print(f"🏆 方式 B (HyDE 假想文档检索) | 命中: [{res_hyde[0].doc_id}] | 余弦相似度: {res_hyde[1]:.4f}(显著提升！)")