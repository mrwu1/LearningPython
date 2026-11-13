import math


def dot_product(vec_a:list[float],vec_b:list[float]) -> float:
    """1.计算分子（点积）：对应维度相乘+和"""
    if len(vec_a) != len(vec_b):
        raise ValueError("两个向量的长度必须一致")
    # <generator object ...>
    return sum(a * b for a,b  in zip(vec_a,vec_b))

def vector_norm(vec:list[float]) -> float:
    """2.计算单个向量的模长（L2范数）"""
    return math.sqrt(sum(x * x for x in vec))

def cosine_similarity(vec_a:list[float],vec_b:list[float]) -> float:
    """3. 计算余弦相似度：点积 / (A的模长 * B的模长)"""
    norm_a = vector_norm(vec_a)
    norm_b = vector_norm(vec_b)
    # 防御性编程：防止零向量除以 0 崩溃
    if norm_a == 0 or norm_b == 0:
        return 0
    return dot_product(vec_a,vec_b) / (norm_a * norm_b)

if __name__ == "__main__":
    # 模拟 4 维语义空间: [住宿特征, 餐饮特征, 交通特征, 违规娱乐特征]
    query_text ="去北京出差住五星级宾馆超标了怎么办？"
    query_vec =  [0.92, 0.05, 0.10, 0.02]

    knowledge_base=[
        {
            "doc_id": "DOC-01",
            "text": "《差旅规范》第三条：一线城市酒店住宿报销上限为450元/晚",
            "vector": [0.95, 0.02, 0.08, 0.01],
        },
        {
            "doc_id": "DOC-02",
            "text": "《差旅规范》第五条：工作日市内打车交通费每日上限150元",
            "vector": [0.04, 0.03, 0.96, 0.01],
        },
        {
            "doc_id": "DOC-03",
            "text": "《反舞弊红线》第一条：严禁报销KTV娱乐、足浴按摩及超市购物卡",
            "vector": [0.01, 0.10, 0.01, 0.98],
        },
        {
            "doc_id": "DOC-04",
            "text": "《差旅规范》第四条：周末加班工作餐上限150元，须附带加班审批单",
            "vector": [0.02, 0.94, 0.03, 0.05],
        },
    ]
    print(f"🔍 用户提问: {query_text}")
    print("-" * 70)

    # 遍历向量库，计算余弦相似度并按得分从高到低排序（这就是最原始的向量数据库检索！）
    scored_docs = []
    for doc in knowledge_base:
        score = cosine_similarity(query_vec,doc.get("vector"))
        scored_docs.append((score,doc))
    # 排序
    scored_docs.sort(key=lambda x: x[0], reverse=True)

    # 展示数据
    # 给列表里每个元素加上序号，产出 (0, 元素0), (1, 元素1), ...。
    for rank,(score,doc) in enumerate(scored_docs,start=1):
        print(f"Top {rank} | 相似度: {score:.4f} | [{doc['doc_id']}] {doc['text']}")