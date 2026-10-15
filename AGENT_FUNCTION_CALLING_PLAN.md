# 🤖 Function Calling 与有效智能体架构（Anthropic Effective Agents）实战指南

> **授课模式**：导师制一对一课件授课 ｜ 随堂手撕原生代码 ｜ 逐行 Code Review ｜ 拒绝死记文档与黑盒框架  
> **适用对象**：具备 Java 工程师背景，正全面转型现代 Python 原生 AI Agent 开发的开发者。  
> **核心原则**：不依赖 LangChain / LlamaIndex 等庞杂黑盒库，纯原生手写打通 OpenAI 报文协议与 Anthropic 可控状态机！

---

## 一、 心智模型对齐（Java vs AI Agent 架构）

| 维度 | Java 体系实现 | AI Agent 体系实现 | 核心心智差异 / 工业落地要点 |
| :--- | :--- | :--- | :--- |
| **工具调用机制** | Feign / gRPC 声明式客户端 | OpenAI **Function Calling** 协议 | 大模型并不直接执行代码，它只负责决策并返回调用的函数名与入参，客户端充当 RPC 代理执行器。 |
| **报文事务对齐** | 请求 ID / Trace ID（全链路追踪） | `tool_call_id`（如 `call_abc123`） | 大模型通过唯一的 `tool_call_id` 与执行结果进行强绑定回传，确保上下文不混淆。 |
| **状态机与工作流** | Spring State Machine / Camunda BPMN | **ReAct 循环 (Reasoning + Acting)** | 思考 ➡️ 行动 ➡️ 观察 ➡️ 再思考，必须配备 `max_iterations` 熔断机制防止死循环。 |
| **任务分解与并行** | Master-Worker / Fork-Join 线程池 | **Orchestrator-Workers（编排者-工人）** | 主模型负责意图拆解与宏观规划，子任务/工具通过 AsyncIO `gather` 极速并发执行，再由主模型汇总裁决。 |
| **架构哲学** | 拒绝黑盒，注重日志、可观测性与重试 | **Anthropic：Simple & Controllable** | 拒绝黑盒自主漫游智能体；生产级 Agent 的核心是状态透明、控制流可控、具备自愈与熔断机制。 |

---

## 二、 学习进度打卡表

| 课时 | 核心知识点 | 状态 | 交付物/代码文件 | 完成时间 |
| :---: | :--- | :---: | :--- | :---: |
| **第 1 课** | 4 种角色定义与 tool_calls 报文往返生命周期 | ✅ 已完成 | `src/agent_study/lesson_01_message_roles.py` | 2026-10-13 |
| **第 2 课** | 工具契约装配与动态分发路由表（Pydantic 深度接力） | ✅ 已完成 | `src/agent_study/lesson_02_tool_registry.py` | 2026-10-13 |
| **第 3 课** | 原生手写 ReAct 闭环与防止死循环熔断保护 | ✅ 已完成 | `src/agent_study/lesson_03_native_react.py` | 2026-10-13 |
| **第 4 课** | Orchestrator-Workers 编排者-工作者架构与并行调度 | ✅ 已完成 | `src/agent_study/lesson_04_orchestrator_workers.py` | 2026-10-13 |
| **第 5 课** | 毕业实战：打造工业级状态透明原生 Agent 引擎 | ✅ 已完成 | `src/agent_study/lesson_05_production_agent.py` | 2026-10-13 |
