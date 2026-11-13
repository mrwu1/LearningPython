from app.indexing.embedding_service import EmbeddingService
from app.ingestion.batch_executor import BatchExecutor
from app.parsers.document_parser import DocumentParser


def run_test():
    print("开始测试 BatchExecutor 批处理入库中枢...")
    # 1. 显式创建底层依赖引擎
    parser = DocumentParser()
    embedder = EmbeddingService(dimensions=1024)
    executor = BatchExecutor(parser, embedder)
    # 1. 检查当前剩余待办数量
    initial_pending = executor.get_pending_count()
    print(f"1. 当前待处理文件总数: {initial_pending}")
    assert initial_pending > 0, "数据库中应至少有 PENDING 状态的文件"

    # 2. 模拟前端触发一个微批次 (处理 2 个文件)
    print("\n2. 正在触发首个微批次 (batch_size = 1)...")
    batch_res = executor.execute_batch(batch_size=1)
    print("\n--- 批次执行报告 ---")
    print(f"实际处理: {batch_res.processed_count} 个")
    print(f"成功入库: {batch_res.success_count} 个")
    print(f"失败数量: {batch_res.failed_count} 个")
    print(f"剩余待办: {batch_res.remaining_pending} 个")

    for item in batch_res.details:
        print(f"  - [{item.status}] 文件: {item.file_name} | 切片数: {item.chunk_count}")

    # 3. 断言验证
    assert batch_res.processed_count == 1
    assert batch_res.remaining_pending == initial_pending - 1

if __name__ == "__main__":
    run_test()