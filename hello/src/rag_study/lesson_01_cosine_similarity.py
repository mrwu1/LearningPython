"""
模块 1 前置数学实验：Embedding 原理、余弦相似度、归一化与距离方向

配置约定：
- 使用硅基流动（SiliconFlow）提供的 Embedding 模型（默认 `BAAI/bge-m3`）。
- API Key、Base URL 与模型名称全部从环境变量 / `.env` 读取，绝不硬编码或打印密钥。
"""

import asyncio
import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import AsyncOpenAI

# 加载 hello/.env 配置文件
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

EMBEDDING_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

# 合成售后规章条款（无敏感信息）
POLICY_CLAUSES: list[dict[str, str]] = [
    {
        "clause_id": "CLAUSE_101",
        "category": "食品安全",
        "content": "【食安赔付】若顾客食用餐品后出现急性胃肠炎、腹泻、呕吐等身体不适，凭二级甲等及以上医院就诊病历及发票，平台执行退一赔十（不足1000元按1000元赔付）。",
    },
    {
        "clause_id": "CLAUSE_102",
        "category": "餐品异物",
        "content": "【异物赔付】若餐品中发现毛发、虫体、塑料碎片等非食材异物，顾客提供清晰照片凭证后，全额退还该菜品费用，并额外发放20元无门槛致歉红包。",
    },
    {
        "clause_id": "CLAUSE_201",
        "category": "配送履约",
        "content": "【超时赔付】骑手实际送达时间超过预计送达时间15分钟至30分钟的，赔付订单实付金额的10%；超过30分钟以上的，赔付订单实付金额的30%。",
    },
    {
        "clause_id": "CLAUSE_301",
        "category": "退单规则",
        "content": "【撤单限制】商家尚未接单时，顾客可无条件全额取消订单；商家已接单且已开始备餐出餐后，非质量问题原则上不支持无理由全额秒退。",
    },
]


def load_embedding_api_key() -> str:
    """读取并校验硅基流动 API Key，禁止在日志或报错中泄露密钥明文"""
    api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
    if not api_key or api_key == "your_siliconflow_api_key_here":
        raise RuntimeError(
            "未配置有效的 SILICONFLOW_API_KEY，请在 hello/.env 中填入你的硅基流动 API Key。"
        )
    return api_key


def compute_cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    任务 1：使用 NumPy 计算两个向量的余弦相似度
    数学公式：Cosine(A, B) = (A · B) / (||A|| * ||B||)
    """
    a = np.array(vec_a, dtype=np.float64)
    b = np.array(vec_b, dtype=np.float64)

    # TODO 1: 使用 np.dot(a, b) 计算向量点积 (Dot Product)
    dot_product = ...

    # TODO 2: 使用 np.linalg.norm() 分别计算向量 a 和向量 b 的模长 (L2 Norm)
    norm_a = ...
    norm_b = ...

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    # TODO 3: 返回余弦相似度 float 值
    return ...


async def get_embeddings(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """
    任务 2：批量调用硅基流动 Embedding 接口，将文本列表转化为向量列表
    """
    # TODO 4: 调用 client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    # 并按顺序提取每个 item.embedding 返回
    ...


async def rank_clauses_by_similarity(
    query_vec: list[float],
    indexed_clauses: list[dict],
) -> list[dict]:
    """
    任务 3：计算查询向量与所有条款的余弦相似度并按降序排列
    注意：相似度不等于正确概率；阈值需在模块 1 开发集上实测标定，不预设通用数值。
    """
    scored_results = []
    for item in indexed_clauses:
        # TODO 5: 调用 compute_cosine_similarity 计算得分并存入 scored_results
        ...

    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results


async def main() -> None:
    api_key = load_embedding_api_key()
    client = AsyncOpenAI(base_url=EMBEDDING_BASE_URL, api_key=api_key)

    print(f"🚀 [Step 1] 正在调用硅基流动 ({EMBEDDING_MODEL}) 对规章条款进行向量化...")
    clause_texts = [c["content"] for c in POLICY_CLAUSES]
    clause_vectors = await get_embeddings(client, clause_texts)

    sample_dim = len(clause_vectors[0])
    sample_norm = float(np.linalg.norm(clause_vectors[0]))
    print(f"✅ 向量化完成！维度: {sample_dim} 维 | 首条向量模长 ||V||: {sample_norm:.4f}\n")

    indexed_clauses = [
        {**clause, "vector": vec}
        for clause, vec in zip(POLICY_CLAUSES, clause_vectors)
    ]

    test_queries = [
        "吃完你们家的麻辣烫我上吐下泻去急诊挂水了，怎么赔偿？",
        "外卖员比预计时间晚了整整40分钟才送到，面都坨了！",
        "商家已经出餐了，但我临时开会不想吃了，能全额退吗？",
        "请问明天杭州西湖区会下暴雨吗？出门要不要带伞？",
    ]

    query_vectors = await get_embeddings(client, test_queries)

    for query, q_vec in zip(test_queries, query_vectors):
        print(f"\n🙋 用户提问: 「{query}」")
        ranked = await rank_clauses_by_similarity(q_vec, indexed_clauses)
        for rank, hit in enumerate(ranked[:2], 1):
            print(
                f"   Top-{rank} [{hit['clause_id']} | {hit['category']}] "
                f"(Cosine: {hit['score']:.4f}) -> {hit['content'][:40]}..."
            )


if __name__ == "__main__":
    asyncio.run(main())
