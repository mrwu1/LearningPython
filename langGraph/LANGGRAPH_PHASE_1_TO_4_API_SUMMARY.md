# LangGraph 核心 API 终极全景脉络手册 (阶段一至阶段四)

> **文档定位**：本手册系统梳理了从基础图状态机内核、受控 ReAct 工具环路、持久化与时间旅行，到现代高阶流控与人机协同的完整 API 知识树与设计心法，专为企业级 AI Agent 架构师提供实战指引与速查字典。

---

## 🗺️ 一、宏观脉络全景图（API 演进大厦）

LangGraph 的 API 体系并非零散工具的拼凑，而是严格遵循 **自底向上的分层防御式架构**：

```
┌────────────────────────────────────────────────────────────────────────┐
│ 5. 人机协同与动态流控层 (Phase 4: interrupt, Command, Send, Subgraphs)  │
├────────────────────────────────────────────────────────────────────────┤
│ 4. 持久化与双层记忆底座 (Phase 3: SqliteSaver/Postgres, Store, update_state)│
├────────────────────────────────────────────────────────────────────────┤
│ 3. 认知大脑与受控工具环路 (Phase 2: bind_tools, ToolNode, tools_condition)│
├────────────────────────────────────────────────────────────────────────┤
│ 2. 图拓扑与 Pregel 调度内核 (Phase 1: StateGraph, add_node, add_edge)  │
├────────────────────────────────────────────────────────────────────────┤
│ 1. 状态与通道契约 (Phase 1: TypedDict, Annotated, Reducer, Pydantic)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 二、五大核心 API 模块分类深剖

### 模块一：状态契约与通道（State & Channel APIs）
> **解决的核心问题**：图在运行时，数据以什么格式在节点之间流动？并发写时如何避免冲突崩溃？

| 核心 API / 语法 | 典型代码示例 | 架构作用与使用心法 |
| :--- | :--- | :--- |
| **`TypedDict`** | `class State(TypedDict):`<br>&nbsp;&nbsp;`messages: list` | **图内部工作状态的标准容器**。轻量无序列化开销，直接支持 Python 原生字典访问，是节点之间传递数据的基础载体。 |
| **`Annotated[T, Reducer]`** | `messages: Annotated[list, add_messages]`<br>`reports: Annotated[list, operator.add]` | **状态通道（State Channel）+ 合并器（Reducer）**。<br>默认字段是覆盖（LastValue）模式；只有声明了 Reducer 的字段，多个节点并发写入时才不会抛出 `InvalidUpdateError`。 |
| **`add_messages`** | `Annotated[list[BaseMessage], add_messages]` | **消息列表专用 Reducer**。具备智能去重与原地更新特性：若新消息的 `id` 与旧消息相同，则原地替换；否则在末尾追加。 |
| **`input_schema` / `output_schema`** | `StateGraph(InternalState, input_schema=InboundDTO, output_schema=OutboundDTO)` | **外部防腐层（Anti-Corruption Layer）**。<br>内部用 `TypedDict` 高性能流转，对外暴露 `Pydantic V2` 强契约校验，过滤敏感字段防止数据泄露。 |

---

### 模块二：图拓扑与 Pregel 编排（Graph Topology APIs）
> **解决的核心问题**：如何把独立的业务函数组装成支持循环、分支与超步（Superstep）的状态机？

| 核心 API / 语法 | 典型代码示例 | 架构作用与使用心法 |
| :--- | :--- | :--- |
| **`StateGraph(State)`** | `builder = StateGraph(State)` | 图构建器基类，绑定核心主状态类型。 |
| **`builder.add_node(name, fn)`** | `builder.add_node("agent", agent_node)`<br>`builder.add_node("sub", compiled_subgraph)` | 注册节点。`fn` 可以是一个普通 Python 函数，也可以是**另一个编译好的子图（Compiled Graph）**！ |
| **`builder.add_edge(u, v)`** | `builder.add_edge(START, "agent")`<br>`builder.add_edge("agent", END)` | **静态确定性边**。`START` 为系统入口虚拟节点，`END` 为终态收敛节点。 |
| **`builder.add_conditional_edges`** | `builder.add_conditional_edges(source, router_func, [targets])` | **动态条件路由边**。`router_func` 根据当前 `state` 动态返回下一个目标节点的字符串标识。第三个参数用于显式声明目的节点清单供校验。 |
| **`builder.compile(...)`** | `app = builder.compile(checkpointer=..., store=...)` | **编译图**。将声明式的节点与边关系固化为 Google Pregel 架构的并发执行运行时。 |

---

### 模块三：受控 Agent 与工具生态（Tool Ecosystem APIs）
> **解决的核心问题**：如何让大模型与外部系统交互，并杜绝死循环与越权提权攻击？

| 核心 API / 语法 | 典型代码示例 | 架构作用与使用心法 |
| :--- | :--- | :--- |
| **`@tool`** | `@tool`<br>`def query_order(order_id: str):` | 声明供 LLM 调用的工具。**必须写英文 docstring** 或显式传递 `description`，因为这是模型的提示词上下文。 |
| **`llm.bind_tools([tools])`** | `llm_with_tools = llm.bind_tools([query_order])` | 将工具 Schema（JSON Schema）挂载到底层大模型上，支持模型输出结构化的 `tool_calls`。 |
| **`ToolNode(tools)`** | `builder.add_node("tools", ToolNode([query_order]))` | **工具执行器节点**。自动解析最新 `AIMessage.tool_calls`，并发执行对应的 Python 函数，并包装成 `ToolMessage` 写回状态。 |
| **`tools_condition`** | `builder.add_conditional_edges("agent", tools_condition)` | **内置路由函数**。检查最后一条消息如果有 `tool_calls` 则返回 `"tools"`，否则返回 `"__end__"`。 |
| **`InjectedState`** | `def my_tool(order_id: str, user_id: Annotated[str, InjectedState("user_id")]):` | **零信任安全防腐**。从运行时状态直接注入当前登录用户的真实身份，大模型对此参数完全不可见，彻底杜绝 IDOR 越权漏洞。 |

---

### 模块四：持久化底座与双层记忆（Persistence & Memory APIs）
> **解决的核心问题**：服务重启对话不丢失？明天来了还能识别用户偏好？如何实现状态回滚？

| 核心 API / 语法 | 典型代码示例 | 架构作用与使用心法 |
| :--- | :--- | :--- |
| **`SqliteSaver` / `AsyncPostgresSaver`** | `checkpointer = SqliteSaver(conn)`<br>`checkpointer = AsyncPostgresSaver(pool)` | **短时间工作记忆（Checkpointer）**。每个超步自动在数据库记录不可变快照。Postgres 首次运行前需调用 `await checkpointer.setup()`。 |
| **`thread_id`** | `config = {"configurable": {"thread_id": "T101"}}` | **会话横向隔离键**。不同租户/用户/会话窗口使用不同的 `thread_id`，底层物理表严格隔离。企业标准：`{tenant_id}:{user_id}:{session_id}`。 |
| **`checkpoint_ns`** | 根图为 `""`，子图为 `"sub_node:uuid"` | **会话纵向隔离键**。在同一个 `thread_id` 内部，主图与子图通过命名空间实现快照隔离，防止状态同名覆盖。 |
| **`app.get_state(config)`** | `snapshot = app.get_state(config)` | **读取最新快照**。获取当前最新状态字典 `snapshot.values`、下一个待执行节点元组 `snapshot.next`。 |
| **`app.get_state_history(config)`** | `history = list(app.get_state_history(config))` | **查看完整历史版本树（时间旅行）**。返回所有历史快照，类似 `git log`。 |
| **`app.update_state(...)`** | `app.update_state(config, values={"amt": 10}, as_node="drafter")` | **篡改/修正状态并派生分支**。不会抹除历史，而是类似 `git checkout -b` 产生一个新的 `checkpoint_id`，指定 `as_node` 伪装触发源。 |
| **`BaseStore` (`InMemoryStore` / `AsyncPostgresStore`)** | `store.put(("users", uid), "pref", {...})`<br>`store.get(("users", uid), "pref")` | **跨会话长期记忆（Long-term Store）**。跨越所有 `thread_id` 永久保留用户画像。通过在节点函数签名声明 `*, store: BaseStore` 自动依赖注入。 |

---

### 模块五：高阶流控与人机协同（Flow Control & HITL APIs）
> **解决的核心问题**：未知数量的任务怎么并发？关键业务怎么挂起等待人工审批？子图怎么解耦？

| 核心 API / 语法 | 典型代码示例 | 架构作用与使用心法 |
| :--- | :--- | :--- |
| **`interrupt(payload)`** | `decision = interrupt({"amount": 250})` | **现代动态断点**。在节点任意代码行直接挂起图执行（类似协程 `yield`）。挂起参数自动暴露在 `snapshot.tasks[0].interrupts[0].value` 中。 |
| **`Command(resume=...)`** | `app.invoke(Command(resume=data), config=config)` | **双向唤醒指令**。外界审批完成后，把数据原样当作 `interrupt()` 的返回值注入回挂起的节点，图原地苏醒继续向下执行。 |
| **`Send(node_name, sub_state)`** | `def map_fn(state):`<br>&nbsp;&nbsp;`return [Send("worker", {"item": i}) for i in state["items"]]` | **动态 Map-Reduce 任务派发**。突破静态边限制，在条件边函数中动态扇出 $N$ 个并发 worker 实例，由 Reducer 同步屏障自动汇总。 |
| **子图嵌入（Subgraphs）** | `parent_builder.add_node("risk", compiled_subgraph)` | **模块化子图解耦**。子图私有内部字段完全封闭在其 `checkpoint_ns` 中，只有父子两方同名的公共契约字段才会被双向同步，零状态污染。 |

---

## ⚡ 三、企业架构师场景速查表（“想做 X 场景 $\rightarrow$ 调哪个 API？”）

| 真实企业业务需求 | 推荐调用的 LangGraph 核心 API 组合 |
| :--- | :--- |
| **1. 多个工作节点同时返回数据，防止被互相覆盖** | `Annotated[list, operator.add]` 或自定义深度合并 Reducer |
| **2. 大额支付/退款/发信，必须等人工确认才执行** | `interrupt(payload)` 挂起 + `Command(resume=decision)` 唤醒 |
| **3. 订单里有未知数量的菜品，需要同时并发核验库存** | 条件边返回 `list[Send("worker_node", item_substate)]` |
| **4. 用户今天关掉网页明天再来，AI 依然记得他的饮食偏好** | `store.put(("users", uid), ...)` 存入画像 + 节点注入 `*, store` |
| **5. 跨部门团队协作，风控团队不想让主流程看到私有打分** | 将风控封装为 `compiled_subgraph`，作为普通节点嵌入主图 |
| **6. 大模型在上一步给出了错误的 SQL，需要人工修正重试** | `get_state_history()` 检索快照 + `update_state(values, as_node=...)` |
| **7. 严格防止恶意用户伪造 `user_id` 越权查看他人数据** | `@tool` 中将身份标识参数声明为 `Annotated[str, InjectedState("uid")]` |
| **8. 多个企业租户共用同一个后端微服务集群，保证数据隔离** | 在运行时配置中指定复合键：`thread_id=f"{tenant_id}:{user_id}:{session_id}"` |

---

## 💡 四、黄金法则与避坑心法

1. **State 是数据高速公路**：图内的所有计算结果必须通过返回字典写回通道，绝不在 Node 外部维护全局可变变量。
2. **区分两种记忆的生命周期**：
   - 任务级工作记忆（当前会话）$\rightarrow$ 归 `Checkpointer` 管；
   - 用户级画像记忆（跨越新会话）$\rightarrow$ 归 `BaseStore` 管。
3. **断点重构选现代标准**：彻底抛弃旧版静态的 `interrupt_before/after`，全面采用行级细粒度的 `interrupt()` 与 `Command(resume=...)`。
4. **单体图尽早微核化**：当主图节点超过 10 个或涉及不同业务团队时，果断拆分为独立子图（Subgraphs），依靠同名键契约进行通信。
