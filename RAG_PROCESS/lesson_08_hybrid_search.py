import math
import re
from typing import Dict, List, Tuple

from lesson_03_chroma_store import MiniChromaCollection
from lesson_05_rag_fusion_rrf import reciprocal_rank_fusion


def tokenize(text:str)->list[str]:
    """极简双轨分词：

    1. 保留连续英文、下划线、中划线和数字（如 INV-2026-001、450元）；
    2. 对中文按单字切分，实现免额外分词包的字符级倒排索引。
    """
    # 提取英文/数字/特定代号
    alphanumeric_tokens = re.findall(r"[a-zA-Z0-9_\-]+", text.lower())
    # 提取中文字符
    chinese_tokens = re.findall(r"[\u4e00-\u9fa5]", text)
    return alphanumeric_tokens + chinese_tokens

class SimpleBM25:
    """纯 Python 白盒实现的 BM25 稀疏检索器 (Sparse Retriever)

    公式：Score(D, Q) = sum( IDF(qi) * (TF * (k1 + 1)) / (TF + k1 * (1 - b + b *  (|D| / avgdl))) )
   """
    def __init__(self,k1:float=1.5, b:float=0.75):
        self.k1 = k1 # 词频饱和度控制参数
        self.b = b # 文档长度归一化惩罚参数
        self.corpus_size=0 # 文档总数
        self.avgdl=0.0 #平均文档长度
        self.doc_tokens:List[List[str]] = [] # 每个文档的分词结果
        self.docs_ids:List[str] = []
        self.df: Dict[str, int] = {}  # 词 -> 包含该词的文档数 (Document Frequency)
        self.idf: Dict[str, float] = {}  # 词 -> 逆文档频率

    def fit(self, ids: List[str], documents: List[str]) -> None:
            """拟合语料库，计算词典、词频与全局 IDF"""
            self.corpus_size = len(documents)
            self.doc_ids = ids
            self.doc_tokens = [tokenize(doc) for doc in documents]
            self.doc_len = [len(tokens) for tokens in self.doc_tokens]
            self.avgdl = (
                sum(self.doc_len) / self.corpus_size if self.corpus_size > 0 else 0
            )

            # 统计 Document Frequency (包含每个词的文档数)
            self.df = {}
            for tokens in self.doc_tokens:
                unique_tokens = set(tokens)
                for token in unique_tokens:
                    self.df[token] = self.df.get(token, 0) + 1

            # 计算逆文档频率 IDF
            self.idf = {}
            for token, freq in self.df.items():
                # 经典 BM25 平滑 IDF 公式: log((N - n + 0.5) / (n + 0.5) + 1)
                self.idf[token] = math.log(
                    (self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0
                )

    def search(self, query: str, top_k: int = 3) -> List[Tuple[str, float]]:
            """计算查询与语料库各文档的 BM25 相关性得分并排序"""
            query_tokens = tokenize(query)
            scores: List[float] = [0.0] * self.corpus_size

            for i, tokens in enumerate(self.doc_tokens):
                cur_len = self.doc_len[i]
                # 计算文档词频 TF
                tf_dict: Dict[str, int] = {}
                for t in tokens:
                    tf_dict[t] = tf_dict.get(t, 0) + 1

                doc_score = 0.0
                for qt in query_tokens:
                    if qt not in tf_dict:
                        continue
                    tf = tf_dict[qt]
                    idf = self.idf.get(qt, 0.0)
                    # BM25 核心公式
                    numerator = tf * (self.k1 + 1.0)
                    denominator = tf + self.k1 * (
                            1.0 - self.b + self.b * (cur_len / self.avgdl)
                    )
                    doc_score += idf * (numerator / denominator)

                scores[i] = doc_score

            # 组合 (doc_id, score) 并按分数从高到低排序
            ranked = sorted(
                zip(self.doc_ids, scores), key=lambda x: x[1], reverse=True
            )
            return ranked[:top_k]

def run_hybrid_search(
            query: str,
            query_vector: List[float],
            bm25: SimpleBM25,
            dense_kb: MiniChromaCollection,
            k_dense: int = 4,
            k_sparse: int = 4,
            rrf_top_k: int = 3,
    ) -> None:
        """执行混合检索：双路并行检索 -> RRF 排名倒数加权融合"""
        print(f"\n🔍 [用户搜索]: '{query}'")

        # 1. 路径 A: Sparse BM25 检索 (精准字符)
        sparse_hits = bm25.search(query, top_k=k_sparse)
        print("   📊 [BM25 检索榜单]:")
        for rank, (doc_id, score) in enumerate(sparse_hits, 1):
            print(f"      Rank {rank}: [{doc_id}] BM25得分={score:.4f}")

            # 2. 路径 B: Dense 向量检索 (语义相似)
        dense_hits = dense_kb.similarity_search_with_score(
            query_vector, k=k_dense, where={"status": "active"}
        )
        print("   🧠 [Dense 向量榜单]:")
        for rank, (rec, sim, _) in enumerate(dense_hits, 1):
            print(f"      Rank {rank}: [{rec.doc_id}] 余弦相似度={sim:.4f}")

            # 3. 构造 RRF 排名输入列表
        # reciprocal_rank_fusion 接受 List[List[str]]，每个子列表是某条检索路径推荐的 doc_id 榜单
            # 3. 构造 RRF 排名输入列表 (传入 VectorRecord 对象)
        sparse_ranked_records = [
                dense_kb._storage[doc_id] for doc_id, _ in sparse_hits
            ]
        dense_ranked_records = [rec for rec, _, _ in dense_hits]

        # 4. RRF 融合排序
        fused_results = reciprocal_rank_fusion(
                [sparse_ranked_records, dense_ranked_records], k=60
        )

        print("   🏆 [Hybrid 混合检索终榜 (RRF 倒数排名融合)]:")
        for rank, (rec, rrf_score) in enumerate(fused_results[:rrf_top_k], 1):
            print(
                f"      Top {rank}: [{rec.doc_id}] RRF得分={rrf_score:.5f} | 文本={rec.document}"
            )


if __name__ == "__main__":
    # 构造极具代表性的企业真实语料：包含精确编号、极易混淆的专票/普票规则、口语餐饮规则
    doc_ids = [
        "INV-001",
        "INV-002",
        "POL-VAT-SPECIAL",
        "POL-VAT-NORMAL",
        "POL-MEAL",
    ]
    documents = [
        "发票代码 1100234，发票号码 INV-2026-001：华为云服务器租赁费，金额12000元。",
        "发票代码 1100235，发票号码 INV-2026-002：行政采购罗技鼠标键盘办公用品，金额300元。",
        "【增值税专用发票管理办法】员工报销时若提供增值税专用发票，必须包含公司完整纳税人识别号与开户行信息，财务予以全额抵扣进项税。",
                       "【增值税普通发票管理办法】员工报销增值税普通发票，只验证抬头是否一致，普通发票不得抵扣进项税额。",
    "【差旅餐饮制度】员工出差期间餐饮补贴标准为每人每天150元，按出差自然天数据实报销。",
    ]

    # 初始化 BM25 稀疏索引
    bm25 = SimpleBM25(k1=1.5, b=0.75)
    bm25.fit(doc_ids, documents)

    # 初始化 Dense 稠密向量索引 (使用 4 维模拟特征向量)
    dense_kb = MiniChromaCollection(name="hybrid_kb")
    # 特征维度设计示意：[发票/采购类, 税务合规类, 餐饮生活类, 专票独有特征]
    simulated_embeddings = [
        [0.90, 0.20, 0.05, 0.10],  # INV-001 (华为云)
        [0.85, 0.15, 0.10, 0.05],  # INV-002 (鼠标)
        [0.40, 0.95, 0.02, 0.90],  # 专票 (税务特征极强)
        [0.40, 0.95, 0.02, 0.10],  # 普票 (与专票语义非常接近，仅专票特征维度低)
        [0.10, 0.05, 0.95, 0.01],  # 餐饮
    ]
    dense_kb.upsert(
        ids=doc_ids,
        documents=documents,
        embeddings=simulated_embeddings,
        metadatas=[{"status": "active"}] * len(doc_ids),
    )

    print("=" * 80)
    print("🚀 场景 1：精准编号检索（痛点：纯向量无法准确定位编号）")
    # 用户明确搜特定的发票号 INV-2026-001
    # 此时 Dense 向量只知道是“发票/采购”，给不出精确编号偏好 [0.88, 0.18, 0.08, 0.08]
    run_hybrid_search(
        query="请调出发票号码为 INV-2026-001 的采购明细",
        query_vector=[0.88, 0.18, 0.08, 0.08],
        bm25=bm25,
        dense_kb=dense_kb,
    )

    print("\n" + "=" * 80)
    print("🚀 场景 2：口语化模糊搜索（痛点：BM25 一字未提导致得分为 0）")
    # 用户提问“中午在外面填饱肚子一顿能花多少”，字面上完全没有“餐饮补贴”、“据实报销”等字样
    # 但 Dense 语义向量精准抓取餐饮维度 [0.08, 0.02, 0.98, 0.01]
    run_hybrid_search(
        query="出差中午在外面吃个快餐填饱肚子一顿能花多少钱？",
        query_vector=[0.08, 0.02, 0.98, 0.01],
        bm25=bm25,
        dense_kb=dense_kb,
    )

    print("\n" + "=" * 80)
    print("🚀 场景 3：精确词 + 业务意图混合检索（Dense + Sparse 强强联合）")
    # 用户提问“增值税专用发票能不能抵扣税”
    # BM25 精确命中“专用发票”，Dense 命中税务合规语义，双路合璧稳居第一！
    run_hybrid_search(
        query="增值税专用发票进项税抵扣规定",
        query_vector=[0.42, 0.96, 0.02, 0.88],
        bm25=bm25,
        dense_kb=dense_kb,
    )