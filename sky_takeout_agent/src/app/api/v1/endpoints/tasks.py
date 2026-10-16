import asyncio
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from loguru import logger

from app.api.deps import UserDep
from app.core.redis_client import redis_client

router = APIRouter(tags=["异步作业中台"])

async def generate_agent_report_worker(task_id: str, prompt: str):
    """后台异步 Worker：模拟大模型执行复杂推演与报表生成"""
    redis_key = f"task:report:{task_id}"
    try:
        logger.info(f"🚀 [Worker] 任务 {task_id} 启动，目标需求: {prompt}")

        # 1. 模拟第一阶段：检索外卖销量数据
        await asyncio.sleep(2)
        await redis_client.hset(redis_key, mapping={"status": "RUNNING", "progress": "30%"})
        logger.info(f"📊 [Worker] 任务 {task_id} 进度: 30%")

        # 2. 模拟第二阶段：大模型多轮总结与财务对账
        await asyncio.sleep(3)
        await redis_client.hset(redis_key, mapping={"status": "RUNNING", "progress": "70%"})
        logger.info(f"🧠 [Worker] 任务 {task_id} 进度: 70%")

        # 3. 模拟第三阶段：生成 Markdown 报告成果
        await asyncio.sleep(2)
        report_content = (
            f"# 苍穹外卖经营诊断报告\n"
            f"- **诊断主题**: {prompt}\n"
            f"- **核心结论**: 招牌辣子鸡复购率达 68% 位居榜首；米饭毛利最高；建议提升周末备料。\n"
            f"- **生成时间**: 2026-10-16\n"
            f"- **智能体版本**: SkyAgent v1.0"
        )
        await redis_client.hset(redis_key, mapping={
            "status": "SUCCESS",
            "progress": "100%",
            "result": report_content
        })
        # 报表在 Redis 保留 1 小时自动过期
        await redis_client.expire(redis_key, 3600)
        logger.info(f"🎉 [Worker] 任务 {task_id} 彻底完成，报表已写入 Redis！")

    except Exception as e:
        logger.error(f"❌ [Worker] 任务 {task_id} 异常中断: {e}")
        await redis_client.hset(redis_key, mapping={"status": "FAILED", "error": str(e)})

class ReportTaskRequest(BaseModel):
    prompt: str

@router.post(
    "/tasks/agent-report",
    status_code=status.HTTP_202_ACCEPTED,
    summary="异步提交大模型长耗时报表任务"
)
async def create_agent_report_task(
    req: ReportTaskRequest,
    bg_tasks: BackgroundTasks,
    user: UserDep
):
    """提交长耗时 Agent 任务：非阻塞，立即返回 TaskID"""
    task_id = str(uuid.uuid4())[:8]
    redis_key = f"task:report:{task_id}"

    # 初始化 Redis 状态
    await redis_client.hset(redis_key, mapping={
        "task_id": task_id,
        "status": "PENDING",
        "progress": "0%",
        "creator": user["username"]
    })

    # 将长任务抛入后台执行，主请求立即放行并返回 202
    bg_tasks.add_task(generate_agent_report_worker, task_id, req.prompt)
    logger.info(f"📥 成功接收用户 [{user['username']}] 的报表任务，已派发 TaskID: {task_id}")

    return {
        "task_id": task_id,
        "status": "PENDING",
        "message": "任务已提交至后台处理中，请通过 TaskID 轮询进度"
    }

@router.get("/tasks/{task_id}", summary="轮询异步长任务状态与最终结果")
async def get_task_status(task_id: str):
    redis_key = f"task:report:{task_id}"
    task_data = await redis_client.hgetall(redis_key)

    if not task_data:
        raise HTTPException(status_code=404, detail="未找到该任务或任务已过期")

    return task_data
