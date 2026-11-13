import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.redis_cache import RedisCacheManager
from app.retrieval.hybrid_retriever import HybridRetriever


def run_cache_benchmark():
    cache = RedisCacheManager()
    retriever = HybridRetriever()
    question = "请问外国人来华商务邀请函怎么办理？"

    # 先递增一次版本号确保从干净的 L2 状态开始，同时清除该问题的 L1 向量缓存以模拟真实冷启动
    cache.bump_corpus_version()
    emb_key = cache._build_emb_key(question, retriever.embedder.model_name, retriever.embedder.dimensions)
    try:
        cache.client.delete(emb_key)
    except Exception:
        pass

    print("\n" + "=" * 75)
    print("阶段 1：冷启动检索 (L1 Miss + L2 Miss -> 调用云端 Embedding + 查 PG)")
    print("=" * 75)
    t0 = time.perf_counter()
    res1 = retriever.retrieve(query=question, top_k=3, mode="hybrid")
    cold_ms = (time.perf_counter() - t0) * 1000
    print(f"冷启动耗时: {cold_ms:.2f} ms | 返回切片数: {len(res1)}")

    print("\n" + "=" * 75)
    print("阶段 2：重复提问热检索 (L2 Hit -> 直接从 Redis 返回结构化切片)")
    print("=" * 75)
    t1 = time.perf_counter()
    res2 = retriever.retrieve(query=question, top_k=3, mode="hybrid")
    hot_ms = (time.perf_counter() - t1) * 1000
    print(f"L2 命中耗时: {hot_ms:.2f} ms | 加速比: {cold_ms / max(hot_ms, 0.01):.1f}x")

    print("\n" + "=" * 75)
    print("阶段 3：模拟新制度入库 (bump_corpus_version -> L2 失效，但 L1 向量缓存仍命中！)")
    print("=" * 75)
    new_ver = cache.bump_corpus_version()
    t2 = time.perf_counter()
    res3 = retriever.retrieve(query=question, top_k=3, mode="hybrid")
    warm_ms = (time.perf_counter() - t2) * 1000
    print(f"当前语料版本: v{new_ver} | L1命中+PG重查耗时: {warm_ms:.2f} ms (免去了云端 Embedding RTT！)")


if __name__ == "__main__":
    run_cache_benchmark()