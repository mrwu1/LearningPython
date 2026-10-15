import time
from types import TracebackType



class ExecutionTimer:
  def __init__(self,operation_name:str):
      self.operation_name = operation_name
      self.start_time:float=0.0

  def __enter__(self)->"ExecutionTimer":
      self.start_time = time.perf_counter()
      return self

  def __exit__(self,
               exc_type: type[BaseException] | None,
               exc_val: BaseException | None,
               exc_tb: TracebackType | None)->bool:
      elapsed_ms = time.perf_counter() - self.start_time
      if exc_type is not None:
          print(f"❌ [Timer] 【{self.operation_name}】失败！耗时: {elapsed_ms:.2f}ms, 原因:{exc_val}")
          return False
      print(f"✅ [Timer] 【{self.operation_name}】成功！耗时: {elapsed_ms:.2f}ms")
      return True


if __name__ == "__main__":
    # 测试场景 A：正常业务执行
    with ExecutionTimer("diff time") as timer:
        time.sleep(0.5)
        print("start counting time")
    # 测试场景 B：异常业务执行
    print("\n------------------------------")
    try:
        with ExecutionTimer("unusual"):
            time.sleep(0.4)
            raise ValueError("your wallet is almost empty")
    except ValueError as e:
        print(f"💡 外层捕获到异常通知: {e}")