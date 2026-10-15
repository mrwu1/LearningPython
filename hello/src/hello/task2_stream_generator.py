# 1. 实现生成器函数 simulate_llm_stream(full_text: str, chunk_size: int = 2)：
#       • 模拟大模型生成文本的过程：不要一次性返回，而是通过 yield 每次吐出 chunk_size 个字符（利用切片
#       full_text[i:i+chunk_size]）；
#       • 每次产出前加上微小的随机延迟（如 0.05 ~ 0.1 秒，使用 time.sleep），模拟真实模型的推理耗时；
#       • 函数返回类型注解使用：from typing import Generator，注解为 Generator[str, None, None]。


import random
from time import sleep


def simulate_llm_stream(full_text: str, chunk_size: int = 2):
    print("Simulating LLM stream...")
    for i in range(0, len(full_text), chunk_size):
        #   sleep(0.1)
        sleep(random.uniform(0.04, 0.08))
        # 核心：交出数据，暂停当前函数栈帧
        yield full_text[i : i + chunk_size]


g = simulate_llm_stream("Hello, my dog is cute", chunk_size=3)
for chunk in g:
    print(chunk, end="", flush=True)


#   2. 实现消费端主函数：
#       • 在控制台实时打印消费内容；
#       • 关键要求：普通 print() 会默认换行，为了实现打字机效果，必须使用 print(chunk, end="",
#       flush=True)（flush=True 会强制刷新标准输出缓冲区，不让字符滞留在内存中）。
def consume_stream():
    for chunk in simulate_llm_stream(
        "Hello, my dog is cute:关键要求：普通 print() 会默认换行，为了实现打字机效果",
        chunk_size=3,
    ):
        print(chunk, end="", flush=True)


if __name__ == "__main__":
    consume_stream()
