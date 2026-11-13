import uuid
from typing import Optional, List, Union

from app.ingestion.jobs.models import IngestJob, JobStatus, JobProgressSummary
from app.ingestion.jobs.repository import JobRepository
from loguru import logger

from app.ingestion.jobs.state_machine import JobStateMachine
from app.ingestion.jobs.progress_tracker import ProgressTracker


class JobManager:
    def __init__(self, repo: Optional[JobRepository] = None):
        self.repo = repo or JobRepository()

    def create_job(self, job_name:str,file_ids:List[int]|None=None,job_uuid:str| None=None):
        job_uuid = job_uuid or str(uuid.uuid4())
        # 1. 幂等检查
        existing_job =self.repo.find_job_by_uuid(job_uuid)
        if existing_job:
            logger.info(f"[JobManager] 命中幂等键: {job_uuid}，直接返回已有作业 #{existing_job.id}")
            return existing_job
        # 2. 查询待挂载文件并落库
        files = self.repo.query_target_files(file_ids)
        return self.repo.insert_job_and_tasks(job_uuid,job_name, files)

    def get_job(self, job_id_or_uuid: Union[int, str]) -> Optional[IngestJob]:
        """获取作业基础信息"""
        if isinstance(job_id_or_uuid, int) or (isinstance(job_id_or_uuid, str) and job_id_or_uuid.isdigit()):
            return self.repo.find_job_by_id(int(job_id_or_uuid))
        return self.repo.find_job_by_uuid(str(job_id_or_uuid))

    def pause_job(self, job_id:int)->bool:
        """暂停作业"""
        job = self.repo.find_job_by_id(job_id)
        if not job:
            return False
        JobStateMachine.validate_transition(job.status, JobStatus.PAUSED)
        return self.repo.update_job_status(job_id, JobStatus.PAUSED)

    def resume_job(self, job_id: int) -> bool:
        """恢复作业"""
        job = self.repo.find_job_by_id(job_id)
        if not job:
            return False
        JobStateMachine.validate_transition(job.status, JobStatus.RUNNING)
        return self.repo.update_job_status(job_id, JobStatus.RUNNING)

    def cancel_job(self, job_id: int) -> bool:
        """取消作业并级联清理子任务"""
        job = self.repo.find_job_by_id(job_id)
        if not job:
            return False
        JobStateMachine.validate_transition(job.status, JobStatus.CANCELLED)
        # 1. 标记 Job 终态
        self.repo.update_job_status(job_id, JobStatus.CANCELLED,set_finished=True)
        # 2. 级联取消所有未完成任务
        self.repo.cancel_tasks_by_job_id(job_id)
        logger.info(f"[JobManager] 作业 #{job_id} 已成功取消，下辖挂起任务已同步终止")
        return True

    def get_job_progress(self, job_id: int) -> Optional[JobProgressSummary]:
        """获取聚合进度摘要"""
        job = self.repo.find_job_by_id(job_id)
        if not job:
            return None
        task_counts = self.repo.get_task_counts_by_status(job_id)
        return ProgressTracker.calculate_summary(job, task_counts)