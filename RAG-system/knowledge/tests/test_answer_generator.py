import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answering.answer_generator import AnswerGenerator


def run_qa_test():
    engine = AnswerGenerator()

    test_cases = [
        ("正例：制度内问题", "请问外国人来华商务邀请函怎么办理？需要准备哪些申请材料？"),
        ("负例：超纲无依据问题", "请问公司员工去火星基地出差的宇航服补贴标准是多少？"),
    ]

    for label, question in test_cases:
        print("\n" + "=" * 85)
        print(f"【{label}】提问: {question}")
        print("=" * 85)
        res = engine.answer(question=question, top_k=4, mode="hybrid")
        print(f"模型: {res.model} | 是否有据: {res.has_evidence}")
        print(f"耗时: 检索 {res.retrieval_ms}ms + 生成 {res.generation_ms}ms = 总计 {res.total_ms}ms")
        print(f"Token: Prompt={res.prompt_tokens}, Completion={res.completion_tokens}")
        print("-" * 85)
        print("【生成回答】:\n" + res.answer)
        print("-" * 85)
        print(f"【服务端核验通过的真实引用 ({len(res.citations)} 条)】:")
        for c in res.citations:
            print(
                f"  [{c.evidence_id}] 《{c.file_name}》(切片#{c.chunk_index}, ChunkID={c.chunk_id}) "
                f"| RRF得分={c.score} (向量:#{c.rank_d}, 全文:#{c.rank_s})"
            )


if __name__ == "__main__":
    run_qa_test()