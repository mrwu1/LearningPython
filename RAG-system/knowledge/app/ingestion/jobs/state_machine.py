from typing import Set, Dict

from app.ingestion.jobs.models import JobStatus
from loguru import logger

class JobStateMachine:
    """控制作业生命周期合规流转的状态机管理器"""
    # 状态转移合法性白名单矩阵
    TRANSITION_RULES: Dict[JobStatus, Set[JobStatus]] = {
        JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.CANCELLED},
        JobStatus.RUNNING: {JobStatus.PAUSED, JobStatus.CANCELLED, JobStatus.COMPLETED, JobStatus.FAILED},
        JobStatus.PAUSED: {JobStatus.RUNNING, JobStatus.CANCELLED},
        JobStatus.COMPLETED: set(),  # 终态，不可跃迁
        JobStatus.FAILED: set(),  # 终态，不可跃迁
        JobStatus.CANCELLED: set(),  # 终态，不可跃迁
    }

    @classmethod
    def can_transition(cls, current_status:JobStatus,target_status: JobStatus):
        """判断当前状态是否允许变更为目标状态"""
        allowed =cls.TRANSITION_RULES[current_status]
        return target_status in allowed

    @classmethod
    def validate_transition(cls, current_status:JobStatus, target_status:JobStatus):
        """强制断言校验，若非法跃迁择抛出业务异常"""
        if not cls.can_transition(current_status, target_status):
            err_msg = f"非法状态跃迁: 无法将状态从 [{current_status.value}] 转为 [{target_status.value}]"
            logger.warning(f"[JobStateMachine] {err_msg}")
            raise ValueError(err_msg)