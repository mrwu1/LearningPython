import time
from concurrent.futures.process import ProcessPoolExecutor


# 1. 模拟一个繁重的 CPU 计算任务（计算几千万次大数累加）
def cpu_heavy_hash(task_id:int)->int:
    total = 0
    for i in range(25_000_000):
        total+=i
    return total

if __name__ == "__main__":
        tasks = [1, 2, 3, 4]
        # --- 实验 1：单进程串行计算 ---
        print("--- 🐢 1. 单进程串行执行 4 个重度计算任务 ---")
        start = time.perf_counter()
        for t in tasks:
            cpu_heavy_hash(t)
        seq_time = time.perf_counter() - start
        print(f"串行总耗时: {seq_time:.2f} 秒")

        print("\n--- 🚀 2. ProcessPoolExecutor 4 进程并行执行 ---")
        start = time.perf_counter()
        # TODO:
        # 1. 使用 with ProcessPoolExecutor(max_workers=4) as executor:
        # 2. 调用 executor.map(cpu_heavy_hash, tasks) 派发任务并获取结果列表
        # 3. 把结果强转为 list(results)
        with ProcessPoolExecutor(max_workers=4) as executor:
            result = executor.map(cpu_heavy_hash,tasks)
            print(list(result))
        pool_time = time.perf_counter() - start
        print(f"多进程总耗时: {pool_time:.2f} 秒")
        print(f"⚡ 性能加速比: {seq_time / pool_time:.2f} 倍！")