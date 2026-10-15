# 🚀 FastAPI 极速工程化与流式 SSE 交付实战指南

> **授课模式**：导师制一对一课件授课 ｜ 随堂手撕原生代码 ｜ 逐行 Code Review ｜ 拒绝死记文档与繁琐配置  
> **适用对象**：具备 Java Spring Boot 工程背景，正全面转型现代 Python AI Agent 与流式 Web 交付的开发者。  
> **核心原则**：大一统串联 Pydantic V2、AsyncIO 协程与 StreamingResponse 流式打字机交付！

---

## 一、 心智模型对齐（Java Spring Boot vs FastAPI）

| 维度 | Java Spring Boot 体系 | 现代 FastAPI 体系 | 核心心智差异 / 生产价值 |
| :--- | :--- | :--- | :--- |
| **应用容器 / 服务器** | 内嵌 Tomcat / Jetty（多线程阻塞模型） | **Uvicorn (ASGI)**（基于 uvloop 的异步事件循环服务器） | 原生异步事件循环驱动，内存占用极小，高并发吞吐极高。 |
| **路由定义** | `@RestController` + `@GetMapping("/path")` | `app = FastAPI()` + `@app.get("/path")` | 无需声明控制器类，直接以模块级装饰器声明路由，极其精炼。 |
| **请求体与校验** | POJO + `@RequestBody` + `@Valid` + 全局异常处理 | 直接声明为已学的 **Pydantic 模型** | 零配置自动反序列化、自动 422 参数拦截与错误定位。 |
| **接口文档生成** | 引入 SpringDoc / Swagger 注解与配置类 | **开箱即用，全自动生成** | 启动即可直接访问 `/docs` (Swagger UI) 和 `/redoc`，零样板代码。 |
| **流式打字机 (SSE)** | `SseEmitter` 或 WebFlux `Flux<ServerSentEvent>` | **`StreamingResponse` + 异步生成器 (`yield`)** | 以 `text/event-stream` 格式极其简单地向前端持续推流。 |

---

## 二、 学习进度打卡表

| 课时 | 核心知识点 | 状态 | 交付物/代码文件 | 完成时间 |
| :---: | :--- | :---: | :--- | :---: |
| **第 1 课** | 初识 FastAPI 与极简路由定义（对标 Spring Controller） | ✅ 已完成 | `src/fastapi_study/lesson_01_first_steps.py` | 2026-10-14 |
| **第 2 课** | Pydantic Request Body 自动校验与零配置 Swagger | ✅ 已完成 | `src/fastapi_study/lesson_02_request_body.py` | 2026-10-14 |
| **第 3 课** | 流式响应 (StreamingResponse) 与 SSE 打字机推送 | ✅ 已完成 | `src/fastapi_study/lesson_03_streaming_sse.py` | 2026-10-14 |
| **第 4 课** | 毕业实战：将 ProductionAgent 封装为流式 Web 微服务 | ✅ 已完成 | `src/fastapi_study/lesson_04_agent_web_service.py` | 2026-10-14 |
