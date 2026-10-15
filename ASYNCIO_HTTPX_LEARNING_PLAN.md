# ⚡ AsyncIO 与 HTTPX 异步高并发实战指南

> **授课模式**：导师制一对一课件授课 ｜ 随堂手撕代码 ｜ 逐行 Code Review ｜ 拒绝死记文档  
> **适用对象**：具备 Java 工程师背景，正全面转型现代 Python 与 AI Agent 高并发开发的开发者。  
> **核心目标**：彻底吃透 Python 单线程事件循环心智、HTTPX 异步连接池与大模型 SSE 流式打字机打通。

---

## 一、 心智模型对齐（Java vs AsyncIO）

| 维度 | Java 传统多线程体系 | Python AsyncIO 现代体系 | 核心心智差异 / Agent 价值 |
| :--- | :--- | :--- | :--- |
| **并发单位** | OS 操作系统线程（Thread） | 协程（Coroutine） | 协程极度轻量（KB 级内存），单线程可支撑数千并发网络连接。 |
| **执行调度模型** | 操作系统抢占式调度（Preemptive） | 单线程协作式事件循环（Cooperative） | 只有当代码主动运行到 `await` 时，才会让渡 CPU 执行权。 |
| **休眠等待** | `Thread.sleep(ms)`（线程被彻底卡死） | `await asyncio.sleep(s)`（非阻塞定时器） | 协程休眠时，事件循环立刻切换去执行其他就绪任务。 |
| **任务组合编排** | `CompletableFuture.allOf(...)` | `asyncio.gather(*tasks)` | 多个大模型或工具并发调用，总耗时取决于最慢的一个。 |
| **网络客户端** | Apache HttpClient / Spring WebClient | `httpx.AsyncClient` | 严禁在异步代码中使用阻塞式 `requests`，必须使用非阻塞套接字。 |
| **流式响应消费** | Spring WebFlux / `SseEmitter` | `async for chunk in resp.aiter_text()` | 异步生成器边接收字节流边渲染打字机效果。 |

---

## 二、 学习进度打卡表

| 课时 | 核心知识点 | 状态 | 交付物/代码文件 | 完成时间 |
| :---: | :--- | :---: | :--- | :---: |
| **第 1 课** | 初识 async 与 await 协程机制 | ✅ 已完成 | `src/async_study/lesson_01_async_await.py` | 2026-10-12 |
| **第 2 课** | gather 并发编排与 return_exceptions 容错 | ✅ 已完成 | `src/async_study/lesson_02_gather_tasks.py` | 2026-10-12 |
| **第 3 课** | 认识 httpx.AsyncClient 与连接池复用 | ✅ 已完成 | `src/async_study/lesson_03_httpx_client.py` | 2026-10-12 |
| **第 4 课** | Agent 多工具并发调用与 Semaphore 限流 | ✅ 已完成 | `src/async_study/lesson_04_concurrency_tools.py` | 2026-10-12 |
| **第 5 课** | 流式响应读取与 aiter_text 打字机输出 | ✅ 已完成 | `src/async_study/lesson_05_stream_response.py` | 2026-10-12 |
| **第 6 课** | 毕业实战：异步高并发 Agent 流式消费闭环 | ✅ 已完成 | `src/async_study/lesson_06_agent_stream_pipeline.py` | 2026-10-13 |
