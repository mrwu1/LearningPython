# 苍穹外卖智能体系统：架构拆分与三大专家（Experts）流程图解

本文档详细拆解了 `sky_takeout_system` 的系统架构，并分别为**点餐/下单推荐（Dish Advisor）**、**外卖派送/履约追踪（Order Manager）**以及**售后退款/动态人机审批（Refund Officer）**三大专员绘制了详细的执行流转图与核心设计说明。

---

## 1. 全局架构与调度中枢（Supervisor Architecture）

整个系统采用 **集中调度（Supervisor-Worker）模式** 与 **闭环裁决机制**。所有的用户请求统一由 `supervisor` 调度，每个专家处理完毕后必须**回传给 `supervisor` 形成闭环**，避免分支逃逸。

```mermaid
flowchart TD
    START([用户输入请求]) --> SV["主管调度中枢 (Supervisor)"]

    subgraph Guards ["主管双重防护守卫"]
        G1{"守卫1: 确定性代码守卫<br/>refund_status in [APPROVED, REJECTED]?"}
        G2["守卫2: LLM 结构化路由决策<br/>with_structured_output(SupervisorDecision)"]
    end

    SV --> G1
    G1 -- "是 (终态已解决)" --> FINISH([结束 flow: __end__])
    G1 -- "否 (未完结)" --> G2

    G2 -- "next_worker: dish_advisor" --> EXP1["专家 1: 点餐推荐专员 (dish_advisor)"]
    G2 -- "next_worker: order_manager" --> EXP2["专家 2: 外卖派送专员 (order_manager)"]
    G2 -- "next_worker: refund_officer" --> EXP3["专家 3: 售后退款专员 (refund_officer)"]
    G2 -- "next_worker: FINISH" --> FINISH

    EXP1 -->|"携带产出回传闭环"| SV
    EXP2 -->|"携带产出回传闭环"| SV
    EXP3 -->|"携带产出回传闭环"| SV

    style G1 fill:#ffebee,stroke:#c62828,stroke-width:2px
    style G2 fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style FINISH fill:#eceff1,stroke:#455a64,stroke-width:2px
```

> [!TIP]
> **主管的“确定性短路守卫”设计**：
> 在 [`supervisor.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/services/agent/supervisor.py#L18-L24) 中，当订单状态已为 `APPROVED` 或 `REJECTED` 时，直接返回 `FINISH`，**不消耗任何大模型 Token，耗时 0ms**，彻底杜绝了大模型在闭环时容易陷入的“死循环分流”。

---

## 2. 专家一：点餐推荐与库存预占（Dish Advisor）

负责处理用户的餐品推荐、热量预算、菜系偏好，并具备真实查询与预占后厨库存的能力。

```mermaid
sequenceDiagram
    autonumber
    actor User as 顾客 (Client)
    participant GW as FastAPI 网关 (/takeout/chat)
    participant Redis as Redis 分布式锁
    participant SV as 主管 (Supervisor)
    participant DA as 点餐推荐专员 (dish_advisor)
    participant Tool as 库存工具 (stock_tool)
    participant MySQL as MySQL (dishes 表)

    User->>GW: "我想吃一份 500 大卡以内的三文鱼轻食"
    GW->>Redis: 加锁 lock:takeout:session:{id} (SET NX EX)
    GW->>SV: 触发状态机，初始路由
    SV->>DA: 路由分流至 dish_advisor
    
    activate DA
    Note over DA,Tool: 结合菜品库与营养规则
    DA->>Tool: 调用 inspect_and_reserve_dish_stock("挪威轻食三文鱼沙拉", 1)
    
    activate Tool
    Tool->>MySQL: SELECT * FROM dishes WHERE name = '...' FOR UPDATE (行排他锁)
    MySQL-->>Tool: stock = 15, prep_time = 12 mins
    Tool->>MySQL: UPDATE dishes SET stock = stock - 1 WHERE id = ...
    Tool-->>DA: 返回 JSON: {"status": "SUCCESS", "in_stock": true, "prep_time_minutes": 12}
    deactivate Tool

    DA->>DA: LLM 生成亲和推荐话术（标明热量、备餐耗时）
    DA-->>SV: 状态追加 [AIMessage], next_worker: "FINISH"
    deactivate DA

    SV->>SV: 检查无其他待办事项，裁决终态
    SV-->>GW: 图流转完成 (__end__)
    GW->>Redis: 释放分布式锁 (Lua Script)
    GW-->>User: SSE 流式输出推荐结果与预订详情
```

### 关键代码落地
* 业务入口：[`src/app/services/agent/specialists/dish_advisor.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/services/agent/specialists/dish_advisor.py)
* 数据库工具：[`src/app/services/agent/tools/stock_tool.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/services/agent/tools/stock_tool.py)
* 仓储层事务行锁：[`src/app/repositories/dish_repo.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/repositories/dish_repo.py#L22-L35)

---

## 3. 专家二：外卖派送与实时履约追踪（Order Manager）

负责处理用户的催单、骑手位置询问、预计到达时间（ETA）计算，查询真实物流传感器数据并安抚顾客。

```mermaid
sequenceDiagram
    autonumber
    actor User as 顾客 (Client)
    participant GW as FastAPI 网关 (/takeout/chat)
    participant SV as 主管 (Supervisor)
    participant OM as 派送追踪专员 (order_manager)
    participant Tool as 物流工具 (courier_tool)
    participant MySQL as MySQL (orders 表)

    User->>GW: "我的外卖到哪了？(ORD-TAKEOUT-9902)"
    GW->>SV: 提交状态机
    SV->>OM: 识别为物流轨迹问题，路由至 order_manager

    activate OM
    OM->>Tool: 调用 query_courier_telemetry(order_number="ORD-TAKEOUT-9902")
    
    activate Tool
    Tool->>MySQL: SELECT courier_name, courier_distance_meters, delivery_eta_minutes FROM orders
    MySQL-->>Tool: 李师傅 | 距离 650 米 | ETA 8 分钟 | 状态: DELIVERING
    Tool-->>OM: 返回结构化 JSON 遥测数据
    deactivate Tool

    OM->>OM: 注入 Prompt: "骑手李师傅距您仅 650 米，预计 8 分钟送达，请稍候！"
    OM-->>SV: 返回 [AIMessage], next_worker: "FINISH"
    deactivate OM

    SV->>SV: 闭环收口，输出最终回复
    SV-->>GW: 完成流转
    GW-->>User: SSE 推送暖心催单答复
```

### 关键代码落地
* 业务入口：[`src/app/services/agent/specialists/order_manager.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/services/agent/specialists/order_manager.py)
* 数据库工具：[`src/app/services/agent/tools/courier_tool.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/services/agent/tools/courier_tool.py)
* 仓储查询：[`src/app/repositories/order_repo.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/repositories/order_repo.py#L12-L18)

---

## 4. 专家三：售后退款与人机协同审批（Refund Officer）

这是整个系统**设计最精妙、最具企业实战价值**的专家模块，融合了**大小额分流、动态人工介入断点（Human-in-the-Loop Interrupt）、状态冻结保存与唤醒恢复、以及财务账本数据库级幂等防重写**。

```mermaid
flowchart TD
    START([顾客发起退款申请]) --> CHECK_IDEM{"幂等检查: refund_status<br/>已为 APPROVED / REJECTED?"}
    
    CHECK_IDEM -- "是" --> REPEAT_REJECT["提示: 该订单已处理完毕，请勿重复提交"] --> RET_SV["返回 Supervisor"]
    CHECK_IDEM -- "否" --> CHECK_AMOUNT{"风控金额研判:<br/>amount <= 50 元?"}

    %% 小额通道
    subgraph FlowA ["通道 A: 小额极速通道 (<= $50)"]
        CHECK_AMOUNT -- "小额" --> AUTO_PAY["调用 payout_tool<br/>执行退款打款"]
        AUTO_PAY --> WRITE_LEDGER["MySQL refund_ledgers 写入财务流水"]
        WRITE_LEDGER --> SET_APP["设置 refund_status = APPROVED"]
        SET_APP --> MSG_AUTO["生成凭证回复: '小额退款已秒级打款'"]
    end

    %% 大额通道
    subgraph FlowB ["通道 B: 大额高危通道 (> $50) - 人机协同 HITL"]
        CHECK_AMOUNT -- "大额" --> PAUSE["触发 interrupt() 动态断点!"]
        PAUSE --> SAVE_PG[("状态机全变量冻结<br/>持久化至 PostgreSQL Checkpointer")]
        SAVE_PG --> SSE_ALERT["FastAPI SSE 下发:<br/>event: human_approval_required"]
        
        SSE_ALERT --> WAIT_HUMAN{{"⏸️ 挂起等待店长审批...<br/>(线程安全休眠，无占用内存/连接)"}}
        
        MGR["👨‍💼 店长后台操作<br/>POST /api/v1/takeout/approve"] --> RESUME["调用 Command(resume=decision)"]
        WAIT_HUMAN -.->|"接收唤醒信号"| RESUME
        
        RESUME --> DECIDE{"店长审核决定?"}
        DECIDE -- "APPROVED (批准)" --> PAY_MGR["按审批金额执行打款<br/>payout_tool"]
        PAY_MGR --> WRITE_LEDGER_B["MySQL 写入退款账本 (附带店长审核备注)"]
        WRITE_LEDGER_B --> SET_MGR_APP["设置 refund_status = APPROVED"]

        DECIDE -- "REJECTED (驳回)" --> SET_MGR_REJ["设置 refund_status = REJECTED"]
    end

    MSG_AUTO --> RET_SV
    SET_MGR_APP --> RET_SV
    SET_MGR_REJ --> RET_SV

    RET_SV --> SV_GUARD{"Supervisor 终态守卫<br/>refund_status 处于终态?"}
    SV_GUARD -- "命中确定性守卫" --> FINISH([__end__ 毫秒退出])

    style FlowA fill:#e8f5e9,stroke:#4caf50
    style FlowB fill:#fff3e0,stroke:#ff9800
    style PAUSE fill:#ffebee,stroke:#f44336,stroke-width:2px
    style WAIT_HUMAN fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px
```

### 大额退款中断与苏醒的时序交互
```mermaid
sequenceDiagram
    autonumber
    actor Customer as 顾客
    participant Gateway as FastAPI 网关
    participant Checkpointer as PostgreSQL 16
    participant RO as 退款专家 (refund_officer)
    actor Manager as 店长 (管理后台)

    Customer->>Gateway: POST /takeout/chat (要求退款 $120)
    Gateway->>RO: 调度至退款专家
    RO->>RO: 检测到 $120 > $50，触发 interrupt({...})
    RO->>Checkpointer: 自动将当前 State 快照保存入 checkpoints 表
    Gateway-->>Customer: SSE 发送事件: human_approval_required (告知已转入人工审批)
    
    Note over Customer,Checkpointer: 智能体挂起休眠，不消耗计算资源，状态安全落盘

    Manager->>Gateway: POST /api/v1/takeout/approve<br/>{decision: "APPROVED", approved_amount: 100, notes: "核实牛排已凉，折价赔偿"}
    Gateway->>Checkpointer: 读取快照并校验挂起任务
    Gateway->>RO: 注入 Command(resume=decision) 苏醒状态机
    
    RO->>RO: 从 interrupt() 语句后苏醒，拿到店长决议
    RO->>Gateway: 执行打款，写入 MySQL 流水表，更新 refund_status="APPROVED"
    Gateway-->>Manager: 返回 HTTP 200 {status: "RESUMED_SUCCESSFULLY"}
```

### 关键代码落地
* 核心断点与苏醒逻辑：[`src/app/services/agent/specialists/refund_officer.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/services/agent/specialists/refund_officer.py#L39-L68)
* 人工审批恢复端点：[`src/app/api/v1/endpoints/approval.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/api/v1/endpoints/approval.py#L9-L47)
* 财务流水幂等落库：[`src/app/repositories/refund_repo.py`](file:///Users/anan/LearningPython/sky_takeout_system/src/app/repositories/refund_repo.py#L13-L58)

---

## 5. 架构核心收益对照表

| 维度 | 单文件/Toy Code 实现 | 本工程生产级解耦实现 |
| :--- | :--- | :--- |
| **数据源** | 内存字典 `global dishes = {}` | 真实 **MySQL 8.0**，Alembic 版本化迁移，行级排他锁 |
| **状态持久化**| 内存 `MemorySaver`（重启即丢） | **PostgreSQL 16** `AsyncPostgresSaver` 连接池，崩溃不丢断点 |
| **并发防护** | `asyncio.Lock()`（仅防单进程） | **Redis 全局分布式锁**，毫秒防抖，集群多副本安全互斥 |
| **人工介入** | 控制台 input() 阻塞主线程 | 原生 **`interrupt()` + `Command(resume=...)`** 异步非阻塞挂起 |
| **流式交互** | 简单字符串拼接返回 | **FastAPI SSE** 复合事件流（节点流转、打字机输出、风控告警） |
| **拓扑流转** | 大模型随意跳转，容易死循环 | **主管双守卫**：确定性业务终态 0ms 短路，彻底杜绝死循环 |
