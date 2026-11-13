"""services/rag/policy_knowledge_base.py

    企业差旅合规知识库底座 (基于 Chroma + BM25 双路索引)
"""
import math
import re
from typing import List, Dict


# 真实企业差旅报销与合规手册全文
ENTERPRISE_POLICY_DOCUMENTS = [
        {
            "clause_id": "POL-HOTEL-SUPER",
            "category": "HOTEL",
            "city_tier": "SUPER",
            "content": (
                "【第四章·住宿标准】超一线城市（北京、上海、广州、深圳）住宿标准：初级员工（JUNIOR）每日上限为450元；"   
                "高级员工（SENIOR）每日上限为650元；总监及以上级别（DIRECTOR）每日上限为1500元。"                        
                "超标20%以内的，须在提交发票时补办部门总监OA电子特批；超标超过20%的，超额部分一律个人自行承担。"
            ),
        },
        {
            "clause_id": "POL-HOTEL-NORMAL",
            "category": "HOTEL",
            "city_tier": "NORMAL",
            "content": (
                "【第四章·住宿标准】除超一线城市外的一般城市住宿标准：初级员工每日上限为350元；"                         
                "高级员工每日上限为500元；总监级别每日上限为1000元。超出部分个人自理。"
            ),
        },
        {
            "clause_id": "POL-MEAL-WEEKEND",
            "category": "MEAL",
            "city_tier": "ALL",
            "content": (
                "【第五章·餐饮标准】工作日加班餐饮补助为每人每天100元；周末因公加班餐饮补助为每人每天150元。"            
                "周末餐饮报销必须在附件中上传OA加班审批单，未附加班审批单的餐饮发票按严重违规驳回，不予报销。"
            ),
        },
        {
            "clause_id": "POL-TRAFFIC-FLIGHT",
            "category": "TRAFFIC",
            "city_tier": "ALL",
            "content": (
                "【第六章·交通出行】国内差旅默认乘坐高铁二等座或飞机经济舱。"                                            
                "未经事前审批私自升舱（升至商务舱/头等舱）产生的超额费用属于不可报销之硬性违规，公司一律不予报销并记入合 规台账。"
            ),
        },
]

# 1. 分词器
def simple_tokenize(text: str) -> List[str]:
    alphanumeric = re.findall(r"[a-zA-Z0-9_\-]+", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fa5]", text)
    return alphanumeric + chinese

# sparse search
class SimpleBM25Searcher:

    def __init__(self, documents: List[Dict[str, str]], k1=1.5, b=0.75):
        self.docs = documents
        self.k1 = k1
        self.b = b
        self.corpus_size = len(documents)
        self.doc_tokens = [simple_tokenize(d["content"]) for d in documents]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avgdl = (
            sum(self.doc_len) / self.corpus_size if self.corpus_size > 0 else 0
        )
        self.df = {}
        for tokens in self.doc_tokens:
            for t in set(tokens):
                self.df[t] = self.df.get(t, 0) + 1
        self.idf = {
            t: math.log((self.corpus_size - f + 0.5) / (f + 0.5) + 1.0)
            for t, f in self.df.items()
        }

    def search(self, query: str, top_k=2) -> List[Dict[str, str]]:
        q_tokens = simple_tokenize(query)
        scores = []
        for i, tokens in enumerate(self.doc_tokens):
            tf_dict = {}
            for t in tokens:
                tf_dict[t] = tf_dict.get(t, 0) + 1
            score = 0.0
            for qt in q_tokens:
                if qt in tf_dict:
                    tf = tf_dict[qt]
                    idf = self.idf.get(qt, 0.0)
                    score += (
                            idf
                            * (tf * (self.k1 + 1.0))
                            / (
                                    tf
                                    + self.k1
                                    * (1.0 - self.b + self.b * (self.doc_len[i] / self.avgdl))
                            )
                    )
            scores.append((self.docs[i], score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scores[:top_k]]

# 3. retriever
class EnterprisePolicyKnowledgeBase:
    """单例模式的规章检索库"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_engine()
        return cls._instance

    def _init_engine(self):
        self.bm25 = SimpleBM25Searcher(ENTERPRISE_POLICY_DOCUMENTS)

    def retrieve_relevant_policy(
            self, category: str, city: str, description: str
    ) -> str:
        """检索最吻合的发票规章条款全文"""
        query = f"{category} {city} {description} 报销标准 上限 违规要求"
        # 按类目预过滤
        filtered = [
            d
            for d in ENTERPRISE_POLICY_DOCUMENTS
            if d["category"] == category or d["category"] == "ALL"
        ]
        if not filtered:
            filtered = ENTERPRISE_POLICY_DOCUMENTS

        searcher = SimpleBM25Searcher(filtered)
        matched = searcher.search(query, top_k=1)
        return matched[0]["content"] if matched else ""
