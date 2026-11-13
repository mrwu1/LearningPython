
from app.indexing.embedding_service import EmbeddingService


def run_embedding_test():
    print("开始测试 EmbeddingService 核心表征引擎...")

    # 1. 实例化服务
    service = EmbeddingService()

    # 2. 测试token计数器
    sample_text = "金柚GEO全球交付协同SOP-V1.1 服务质量事故处理办法"
    # token_cnt = service.count_token(sample_text)
    # print(f"1. Token 计数测试通过: '{sample_text}' -> {token_cnt} tokens")

    # 2. 测试单条 Query 向量化
    query = "发生三级事故如何扣罚？"
    # query_vec = service.embedding_query(query)
    # print(f"2. Query 向量化测试通过: 向量维度 = {len(query_vec)}")

    # 3. 测试批量文档向量化 (Micro-batching)
    docs = [
        "第一条：为规范员工差旅管理，特制定本办法。",
        "第二条：波兰国别签证需提供加盖公章的在职证明。",
        "第三条：香港Payroll项目需统一按时申报MPF强积金。"
    ]
    doc_vectors = service.embed_document(docs)
    print(f"3. 批量文档向量化测试通过: 成功计算 {len(doc_vectors)} 个切片")
    assert len(doc_vectors) == 3

if __name__ == "__main__":
    run_embedding_test()