import time


def count_stream():
    print("Counting stream...")
    yield "第一块数据"
    time.sleep(1)
    yield "第二块数据"
    time.sleep(1)
    yield "第三块数据"


gen = count_stream()
for chunk in gen:
    print(chunk)
