"""
    批次摄取数据契约模型 (Job & Task Data Models)
    定义作业与任务的状态机枚举及 Pydantic 实体模型。
    """
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """批次作业状态机枚举"""
    PENDING = "PENDING"  # 待调度
    RUNNING = "RUNNING"  # 运行中 (Worker 正在处理子任务)
    PAUSED = "PAUSED"  # 已暂停 (Worker 停止领取新任务)
    CANCELLED = "CANCELLED"  # 已取消 (所有未完成子任务已中断)
    COMPLETED = "COMPLETED"  # 全部成功完成
    FAILED = "FAILED"  # 批次整体异常终止


class TaskStatus(str, Enum):
    """单文件任务状态机枚举"""
    PENDING = "PENDING"  # 待领取
    RUNNING = "RUNNING"  # Worker 处理中 (持有有效租约)
    COMPLETED = "COMPLETED"  # 切片入库成功
    FAILED = "FAILED"  # 超过最大重试次数失败
    CANCELLED = "CANCELLED"  # 随所属作业级联取消


class IngestJob(BaseModel):
    """批次作业实体"""
    id: int
    job_uuid: str
    job_name: str
    status: JobStatus
    total_files: int
    completed_files: int
    failed_files: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class IngestTask(BaseModel):
    """单文件任务实体"""
    id: int
    job_id: int
    file_id: int
    file_name: str
    status: TaskStatus
    attempt: int
    max_attempts: int
    claim_token: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobProgressSummary(BaseModel):
    """聚合统计进度摘要实体 (可直接作为前端 API 响应)"""
    job_id: int
    status: JobStatus
    total_files: int
    completed_files: int
    failed_files: int
    running_files: int
    pending_files: int
    cancelled_files: int
    progress_percent: float
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_seconds: Optional[float] = None