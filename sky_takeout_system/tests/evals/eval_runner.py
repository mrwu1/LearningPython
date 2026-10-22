import asyncio
import sys
import time
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
# 把项目根目录与当前 evals 目录都加入搜索路径
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR))
from langchain_core.messages import HumanMessage, AIMessage  # 👈 导入 AIMessage
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from app.services.agent.graph_factory import create_sky_takeout_graph
from tests.evals.golden_dataset import GOLDEN_DATASET, EvalTestCase


async def evaluate_single_case(graph, test_case: EvalTestCase) -> dict:
    """
    Executes a single test case through the multi-agent graph,
    measuring latency, routing accuracy, and security constraints.
    """
    thread_id = f"eval_{test_case.case_id}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_input = {
        "trace_id": f"trace_{test_case.case_id}",
        "messages": [HumanMessage(content=test_case.user_query)],
        "order_id": test_case.order_id or "UNKNOWN",
        "user_id": "EVAL_USER_001",
        "next_worker": "dish_advisor",
        "stock_reports": [],
        "refund_amount": test_case.refund_amount,
        "refund_reason": test_case.refund_reason,
        "refund_status": test_case.initial_refund_status or "NONE",
        "reviewer_notes": "",
    }

    start_time = time.perf_counter()
    errors = []
    actual_worker = "UNKNOWN"
    output_text = ""

    try:
        final_state = await graph.ainvoke(initial_input, config=config)

        # 1. 获取轨迹中真正执行回复的专员 (Trajectory Attribution)
        messages = final_state.get("messages", [])
        last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)

        if last_ai_message:
            # 如果专员回复了，以专员的名字为准
            actual_worker = getattr(last_ai_message, "name", "specialist") or "specialist"
            output_text = last_ai_message.content
        else:
            # 如果没有产生 AI 消息（如被中途挂起或直接退出），取 state 中的 next_worker
            actual_worker = final_state.get("next_worker", "FINISH")
            output_text = ""

        # 2. 断言调度命中专员
        if actual_worker != test_case.expected_worker:
            errors.append(
                f"Routing mismatch: Expected '{test_case.expected_worker}', got '{actual_worker}'"
            )

        # 3. 仅对 AI 的真实输出进行安全敏感词扫描 (杜绝误报用户提问)
        if output_text:
            for forbidden in test_case.forbidden_keywords:
                if forbidden.lower() in output_text.lower():
                    errors.append(f"Security Alert: Forbidden keyword '{forbidden}' leaked in AI response!")

    except Exception as e:
        errors.append(f"Execution Exception: {str(e)}")

    latency_ms = (time.perf_counter() - start_time) * 1000

    return {
        "case_id": test_case.case_id,
        "category": test_case.category,
        "expected": test_case.expected_worker,
        "actual": actual_worker,
        "passed": len(errors) == 0,
        "errors": errors,
        "latency_ms": latency_ms,
        "description": test_case.description,
    }


async def run_enterprise_agent_evals():
    """
    Enterprise Evals Runner & CI/CD Release Gatekeeper.
    Aggregates batch test metrics and strictly enforces >= 90% routing accuracy & 0 security failures.
    """
    print("\n" + "=" * 80)
    print(" 🚀 STARTING ENTERPRISE AGENT EVALUATION BENCHMARK (CI/CD GATEKEEPER)")
    print("=" * 80)

    # Use pure in-memory checkpointer for fast isolated testing
    graph = create_sky_takeout_graph(checkpointer=MemorySaver())

    # Execute all test cases concurrently
    tasks = [evaluate_single_case(graph, case) for case in GOLDEN_DATASET]
    results = await asyncio.gather(*tasks)

    # 统计指标
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    accuracy = (passed / total) * 100
    avg_latency = sum(r["latency_ms"] for r in results) / total

    # 打印逐条执行清单
    print("\n📋 EVALUATION RESULTS BREAKDOWN:")
    print("-" * 80)
    for r in results:
        status_icon = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"[{status_icon}] {r['case_id']:<14} | Category: {r['category']:<22} | Latency: {r['latency_ms']:>6.1f}ms")
        print(f"       👉 Expected: {r['expected']:<14} | Actual: {r['actual']:<14} | {r['description']}")
        if r["errors"]:
            for err in r["errors"]:
                print(f"       🚨 ERROR: {err}")
    print("-" * 80)

    # 打印汇总看板
    print("\n" + "=" * 80)
    print(" 📊 ENTERPRISE EVALUATION METRICS DASHBOARD")
    print("=" * 80)
    print(f"  Total Test Cases   : {total}")
    print(f"  Passed Cases       : {passed}")
    print(f"  Failed Cases       : {failed}")
    print(f"  Routing Accuracy   : {accuracy:.1f}%")
    print(f"  Average Latency    : {avg_latency:.1f}ms")
    print("=" * 80)

    # CI/CD 质量门禁断言：准确率 >= 90% 且 0 安全违规
    MIN_ACCURACY_THRESHOLD = 90.0
    if accuracy >= MIN_ACCURACY_THRESHOLD and failed == 0:
        print("\n🎉 [RELEASE GATE PASSED] Quality threshold satisfied! Safe to deploy to production.")
        print("=" * 80 + "\n")
        return 0
    else:
        print(f"\n🛑 [RELEASE GATE BLOCKED] Accuracy ({accuracy:.1f}%) < {MIN_ACCURACY_THRESHOLD}% or regressions detected!")
        print("=" * 80 + "\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_enterprise_agent_evals())
    sys.exit(exit_code)