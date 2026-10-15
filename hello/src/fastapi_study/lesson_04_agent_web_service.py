import asyncio
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

# ==============================================================================
# 1. 契约模型定义（Pydantic V2）
# ==============================================================================

class EmpQueryArgs(BaseModel):
    emp_name: str = Field(..., description="员工姓名，如：张三")

class DeptQueryArgs(BaseModel):
    department: str = Field(..., description="部门名称，如 'AI实验室'")

class AgentChatRequest(BaseModel):
    query: str = Field(..., min_length=2, description="用户发给 Agent 的任务指令")

class AgentEvent(BaseModel):
    step: int = Field(..., description="当前执行轮次")
    stage: str = Field(..., description="生命周期阶段：thought | tool_call | observation | answer")
    content: str = Field(..., description="事件详情或者输出内容")


# ==============================================================================
# 2. 具备流式能力的 StreamingProductionAgent
# ==============================================================================

class StreamingProductionAgent:
    def __init__(self, system_prompt: str, max_iterations: int = 5):
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self._tools = {}  # 统一使用 _tools 存储工具路由表

    def register_tool(self, name: str, description: str, args_model: type[BaseModel]):
        def decorator(func):
            self._tools[name] = {
                "func": func,
                "args_model": args_model,
                "description": description
            }
            return func
        return decorator

    def get_tools_schema(self) -> list[dict]:
        return [
            {
                "name": name,
                "description": info["description"],
                "parameters": info["args_model"].model_json_schema()
            }
            for name, info in self._tools.items()
        ]

    def execute_tool(self, name: str, arguments_json: str) -> str:
        if name not in self._tools:
            return f"错误：未注册的工具 '{name}'"
        tool_info = self._tools[name]
        try:
            # 修正：Pydantic V2 标准反序列化方法为 model_validate_json
            parsed_args = tool_info["args_model"].model_validate_json(arguments_json)
            return tool_info["func"](**parsed_args.model_dump())
        except Exception as e:
            return f"工具参数校验失败: {e}"

    def mock_llm_brain(self, messages: list[dict]) -> dict:
        last_msg = messages[-1]
        if last_msg["role"] == "user":
            return {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_001",
                    "function": {"name": "query_employee", "arguments": '{"emp_name": "张三"}'}
                }]
            }
        if last_msg["role"] == "tool" and last_msg["tool_call_id"] == "call_001":
            return {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_002",
                    "function": {"name": "query_department_project", "arguments": '{"department": "AI实验室"}'}
                }]
            }
        if last_msg["role"] == "tool" and last_msg["tool_call_id"] == "call_002":
            return {
                "role": "assistant",
                "content": "根据最新数据，张三在【AI实验室】主导【自研Agent引擎】，进度已达 95%！",
                "tool_calls": None
            }
        return {"role": "assistant", "content": "任务已完成。", "tool_calls": None}

    # 🌟 核心：异步流式生成器 stream_run
    async def stream_run(self, user_query: str):
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_query}
        ]
        step = 1
        while step <= self.max_iterations:
            await asyncio.sleep(0.4)  # 模拟思考延迟

            llm_response = self.mock_llm_brain(messages)
            tool_calls = llm_response.get("tool_calls")

            # 分支 A：终态达成，产出最终答案
            if not tool_calls:
                final_answer = llm_response.get("content", "")
                event = AgentEvent(step=step, stage="answer", content=final_answer)
                yield f"data: {event.model_dump_json()}\n\n"
                break  # 退出循环，防止后续遍历 None 抛出异常

            # 分支 B：模型决策调用工具
            messages.append(llm_response)
            thought_event = AgentEvent(
                step=step,
                stage="thought",
                content=f"大模型正在决策调用 {len(tool_calls)} 个业务工具..."
            )
            yield f"data: {thought_event.model_dump_json()}\n\n"

            for call in tool_calls:
                call_id = call["id"]
                func_name = call["function"]["name"]
                args_str = call["function"]["arguments"]

                # 阶段 2：通知前端开始调用工具
                await asyncio.sleep(0.3)
                call_event = AgentEvent(
                    step=step,
                    stage="tool_call",
                    content=f"准备调用工具 [{func_name}] 参数: {args_str}"
                )
                yield f"data: {call_event.model_dump_json()}\n\n"

                # 执行本地工具
                result = self.execute_tool(func_name, args_str)

                # 阶段 3：通知前端工具执行结果
                await asyncio.sleep(0.3)
                obs_event = AgentEvent(
                    step=step,
                    stage="observation",
                    content=f"工具 [{func_name}] 返回结果: {result}"
                )
                yield f"data: {obs_event.model_dump_json()}\n\n"

                messages.append({"role": "tool", "tool_call_id": call_id, "content": result})

            step += 1

        # 推送业界统一的流结束标志
        yield "data: [DONE]\n\n"


# ==============================================================================
# 3. 初始化 Agent 与挂载本地业务工具
# ==============================================================================

agent = StreamingProductionAgent(
    system_prompt="你是一个企业级 HR & 研发项目管理智能中枢助手。",
    max_iterations=5
)

@agent.register_tool(
    name="query_employee",
    description="查询员工所在部门和岗位信息",
    args_model=EmpQueryArgs)
def query_employee(emp_name: str) -> str:
    db = {"张三": "所属部门: AI实验室, 岗位: 资深AI架构师"}
    return db.get(emp_name, f"未找到员工 {emp_name}")

@agent.register_tool(
    name="query_department_project",
    description="查询指定部门的核心研发项目及进度",
    args_model=DeptQueryArgs)
def query_department_project(department: str) -> str:
    db = {"AI实验室": "核心项目: 自研企业级Agent引擎, 研发进度: 95%"}
    return db.get(department, f"未找到部门 {department} 的项目记录")


# ==============================================================================
# 4. 创建 FastAPI 应用并挂载流式路由
# ==============================================================================

app = FastAPI(title="生产级流式 Agent 微服务", version="1.0.0")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ProductionAgent Service"}

@app.get("/api/v1/agent/tools")
async def list_tools():
    """查看当前 Agent 挂载的工具列表及 JSON Schema"""
    return {"count": len(agent._tools), "tools": agent.get_tools_schema()}

@app.post("/api/v1/agent/chat")
async def chat_with_agent(req: AgentChatRequest):
    """流式 Agent 交互端点：以 text/event-stream 输出实时思考与工具调用链"""
    return StreamingResponse(
        agent.stream_run(req.query),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("lesson_04_agent_web_service:app", host="127.0.0.1", port=8000, reload=True)