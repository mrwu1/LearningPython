import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.hybrid_retriever import HybridRetriever


def run_test():
    retriever = HybridRetriever(rrf_k=60, recall_k=20)
    question = "请问外国人来华商务邀请函怎么办理？"

    for mode in ["hybrid"]:
        print("\n" + "=" * 80)
        print(f"测试检索模式: [{mode.upper()}] | 提问: {question}")
        print("=" * 80)
        chunks = retriever.retrieve(query=question, top_k=3, mode=mode)
        for idx, c in enumerate(chunks, start=1):
            preview = c.content.replace("\n", " ")[:60]
            print(
                f"Top-{idx} | ID:{c.chunk_id:<4} | 主得分:{c.score:<8} "
                f"(向量:#{c.rank_d} {c.dense_score} | 全文:#{c.rank_s} {c.sparse_score})\n"
                f"      来源: {c.file_name} (切片#{c.chunk_index})\n"
                f"      内容: {preview}..."
            )


if __name__ == "__main__":
    run_test()