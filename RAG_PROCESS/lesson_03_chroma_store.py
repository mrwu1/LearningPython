from dataclasses import dataclass, field
from typing import Any

import math


@dataclass
class VectorRecord:
    """向量数据库底层的四元组存储结构"""
    doc_id:str
    document:str
    embedding:list[float]
    metadata:dict[str,Any] = field(default_factory=dict)

class MiniChromaCollection:
    """
    白盒复刻 ChromaDB / PGVector 核心存储引擎：
    支持：1. upsert 幂等入库  2. metadata 元数据预过滤 (where)  3. 带分检索 (相似度 & 余弦距离)
    """
    def __init__(self,name:str):
        self.name = name
        # 底层用dict,按照doc_id索引，天然支持0(1)幂等覆盖更新（Upsert）
        self._storage: dict[str,VectorRecord] ={}

    @staticmethod
    def _cosine_similarity(vec_a:list[float],vec_b:list[float]) -> float:
        norm_a = math.sqrt(sum([v*v for v in vec_a]))
        norm_b = math.sqrt(sum([v*v for v in vec_b]))
        if norm_a == 0 or norm_b == 0:
            return 0
        return sum(a * b for a, b in zip(vec_a, vec_b)) / (norm_a * norm_b)

    def upsert(
            self,
            ids:list[str],
            documents:list[str],
            embeddings:list[float],
            metadatas:list[dict[str,Any]]|None = None,
    )->None:
        """
          工业级幂等写入 (Upsert)：
           如果 doc_id 已存在则原地更新，绝不产生重复切片克隆体！
        """
        metadatas = metadatas or [{} for _ in ids]
        for doc_id, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
            self._storage[doc_id]=VectorRecord(
                doc_id=doc_id,
                document=doc,
                embedding=emb,
                metadata=meta
            )

    def count(self)->int:
            return len(self._storage)

    @staticmethod
    def _match_metadata(record_meta: dict[str, Any], where: dict[str, Any] | None) -> bool:
        """元数据预过滤器（等价于 SQL 的 WHERE 子句）"""
        if not where:
            return True
        for key, expected_val in where.items(): # [('category', 'food'), ('status', 'active')]
            if record_meta.get(key) != expected_val:
                return False
        return True

    def similarity_search_with_score(
                self,
                query_embedding: list[float],
                k: int = 3,
                where: dict[str, Any] | None = None,
    ) -> list[tuple[VectorRecord, float, float]]:
            """
            核心检索管道：
            第 1 步：先执行 Metadata 预过滤 (Pre-filtering) 缩小候选集；
            第 2 步：对过滤后的候选集计算余弦相似度与余弦距离 (distance = 1 - similarity)；
            第 3 步：按相似度降序（即距离升序）返回 Top-K。
            """
            candidates = []
            for record in self._storage.values():
                # 👉 第一步（第 81 行：守门员查户口）：先看 metadata 标签满不满足 where 条件！
                # 1. 元数据硬过滤：不满足 where 条件的直接跳过，连向量都不用算！
                if not self._match_metadata(record.metadata, where):
                    continue

                # 2. 计算余弦相似度与 Chroma 标准余弦距离
                # 👉 第二步（第 85~87 行：算分）：只有通过了标签过滤的“合格候选人”，才跟问题算余弦相似度！
                sim = self._cosine_similarity(query_embedding, record.embedding)
                cosine_distance = 1.0 - sim
                candidates.append((record, sim, cosine_distance))

            # 3. 按相似度从高到低排序，截取前 k 个 - Top K
            candidates.sort(key=lambda item: item[1], reverse=True)
            return candidates[:k]

if  __name__ == '__main__':
    collection = MiniChromaCollection(name="corporate_expense_policies")
    # 4 维特征空间: [住宿特征, 餐饮特征, 交通特征, 金額/超标敏感度]
    ids = ["POL-HOTEL-SUPER", "POL-HOTEL-OLD", "POL-MEAL-WEEKEND", "POL-TAXI-DAILY"]
    docs = [
        "【2026新版】超一线城市（北上广深）初级员工酒店住宿上限为450元/晚。",
        "【2020废止版】超一线城市初级员工酒店住宿上限为300元/晚。",
        "周末加班餐饮报销上限为150元/天，无加班审批单一律严禁报销。",
        "工作日市内打车交通费每日报销上限为150元。",
    ]
    vecs = [
        [0.92, 0.02, 0.05, 0.85],  # 2026版酒店规定
        [0.93, 0.02, 0.05, 0.86],  # 2020废止版酒店规定（注意：它的字面向量跟问题几乎一样高！）
        [0.05, 0.95, 0.02, 0.80],  # 周末餐饮规定
        [0.04, 0.03, 0.96, 0.75],  # 市内打车规定
    ]
    metas = [
        {"category": "HOTEL", "status": "active", "year": 2026},
        {"category": "HOTEL", "status": "deprecated", "year": 2020},  # 已废止制度！
        {"category": "MEAL", "status": "active", "year": 2026},
        {"category": "TAXI", "status": "active", "year": 2026},
    ]
    # 1. 验证 Upsert 幂等性：连续写入两次，库里依然只有 4 条记录，不会翻倍成 8 条！
    collection.upsert(ids=ids, documents=docs, embeddings=vecs, metadatas=metas)
    collection.upsert(ids=ids, documents=docs, embeddings=vecs, metadatas=metas)
    print(f"✅ 连续两次 Upsert 后，库内文档总数: {collection.count()} 条 (幂等防重生效！)\n")

    #提问：❓❓❓
    query_vec = [0.94, 0.01, 0.04, 0.88]  # 用户问："北京出差住酒店最高能报销多少？"
    print("=" * 80)
    print("❌ 实验 A：不加 Metadata 过滤裸搜 —— 2020年已废止的旧制度排到了第 1 名，引发大模型幻觉！")
    print("=" * 80)

    for rec, sim, dist in collection.similarity_search_with_score(query_vec, k=2):
        print(f"幻觉产生：[{rec.doc_id}] 相似度={sim:.4f} | 距离={dist:.4f} | meta={rec.metadata} -> {rec.document}")


    print("\n" + "=" * 80)
    print("🏆 实验 B：加上 Metadata 过滤 where={'category': 'HOTEL', 'status': 'active'} —— 精准命中现行制度！")
    print("=" * 80)
    for rec, sim, dist in collection.similarity_search_with_score(
            query_vec,
            k=2,
            where={"category": "HOTEL", "status": "active"},
    ):
        print(f"[{rec.doc_id}] 相似度={sim:.4f} | 距离={dist:.4f} | meta={rec.metadata} -> {rec.document}")