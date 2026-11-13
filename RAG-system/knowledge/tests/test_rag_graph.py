import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answering.rag_graph import RAGWorkflow


def run_postgres_checkpoint_test():
    # 生成一个唯一的测试会话 ID，可在 DataGrip 的 public.checkpoints 表中按此 thread_id 查询
    session_id = f"pg-session-{uuid.uuid4().hex[:6]}"
    print(f"本次测试会话 ID (thread_id): {session_id}")

    # =========================================================================
    # 阶段 1：创建第 1 个工作流实例，发起首轮提问，随后销毁实例（模拟后端重启）
    # =========================================================================
    print("\n" + "=" * 85)
    print("【第 1 轮 · 实例 A】首轮提问（状态将自动写入 PostgreSQL checkpoints 表）")
    print("=" * 85)
    workflow_a = RAGWorkflow()
    q1 = "外国人来华商务邀请函怎么办理？"
    res1 = workflow_a.ask(question=q1, session_id=session_id, top_k=3, mode="hybrid")
    print(f"员工提问  : {q1}")
    print(f"独立检索句: {res1.rewritten_query}")
    print(f"自省状态  : {res1.grade_status} | 重检索次数: {res1.retry_count}")
    print(f"助手回答  :\n{res1.answer}\n")

    # 关闭实例 A 的连接池并删除对象，模拟进程重启内存清空
    workflow_a.pool.close()
    del workflow_a
    print("💥 已销毁实例 A（模拟服务重启，内存清空）...")

    # =========================================================================
    # 阶段 2：创建全新的实例 B，用同一个 session_id 发起代词追问
    # =========================================================================
    print("\n" + "=" * 85)
    print("【第 2 轮 · 全新实例 B】代词追问（验证从 PostgreSQL 跨实例恢复历史并消解代词‘它’）")
    print("=" * 85)
    workflow_b = RAGWorkflow()
    q2 = "那它需要准备哪些申请材料？"
    res2 = workflow_b.ask(question=q2, session_id=session_id, top_k=3, mode="hybrid")
    print(f"员工追问  : {q2}")
    print(f"改写后查询: {res2.rewritten_query}  <-- 观察‘它’是否被自动替换为商务邀请函！")
    print(f"自省状态  : {res2.grade_status} | 重检索次数: {res2.retry_count}")
    print(f"核验引用  : {[c.evidence_id + ':' + c.file_name for c in res2.citations]}")
    print(f"助手回答  :\n{res2.answer}\n")

    # =========================================================================
    # 阶段 3：发起超纲无依据提问，验证 CRAG 自省重检索回路与安全拒答
    # =========================================================================
    print("\n" + "=" * 85)
    print("【第 3 轮 · 实例 B】超纲提问（验证 3 号工位判定 IRRELEVANT -> 重试 1 次 -> 安全拒答）")
    print("=" * 85)
    q3 = "请问公司员工去木星空间站出差的补贴标准是多少？"
    res3 = workflow_b.ask(question=q3, session_id=session_id, top_k=3, mode="hybrid")
    print(f"员工提问  : {q3}")
    print(f"重试后查询: {res3.rewritten_query}")
    print(f"自省状态  : {res3.grade_status} | 累计重检索计数: {res3.retry_count}")
    print(f"是否有据  : {res3.has_evidence}")
    print(f"助手回答  : {res3.answer}")

    workflow_b.pool.close()


if __name__ == "__main__":
    run_postgres_checkpoint_test()