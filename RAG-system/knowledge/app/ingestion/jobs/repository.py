"""
    批次作业持久化仓储 (Job Repository)
    纯 SQL 数据访问层，负责 kb_ingest_job 与 kb_ingest_task 的原子增删改查。
    """
import logging
from typing import List, Dict, Any, Optional, Tuple
from psycopg2.extras import execute_batch

from app.db.connection import get_db_connection
from app.ingestion.jobs.models import IngestJob, IngestTask, JobStatus, TaskStatus

logger = logging.getLogger(__name__)

class JobRepository:
    """纯数据库操作：CURD操作"""
    @staticmethod
    def find_job_by_uuid(job_uuid: str) -> Optional[IngestJob]:
        """按 UUID 幂等键查询作业"""
        sql = """
                        SELECT id, job_uuid, job_name, status, total_files, completed_files, failed_files,
                               created_at, started_at, finished_at
                        FROM kb.kb_ingest_job
                        WHERE job_uuid = %s;
                    """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (job_uuid,))
                row = cur.fetchone()
                if not row:
                    return None
                return IngestJob(
                    id=row[0], job_uuid=row[1], job_name=row[2], status=JobStatus(row[3]),
                    total_files=row[4], completed_files=row[5], failed_files=row[6],
                    created_at=row[7], started_at=row[8], finished_at=row[9]
                )

    @staticmethod
    def find_job_by_id(job_id: int) -> Optional[IngestJob]:
        """按数据库主键 ID 查询作业"""
        sql = """
                    SELECT id, job_uuid, job_name, status, total_files, completed_files, failed_files,
                           created_at, started_at, finished_at
                    FROM kb.kb_ingest_job
                    WHERE id = %s;
                """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (job_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return IngestJob(
                    id=row[0], job_uuid=row[1], job_name=row[2], status=JobStatus(row[3]),
                    total_files=row[4], completed_files=row[5], failed_files=row[6],
                    created_at=row[7], started_at=row[8], finished_at=row[9]
                )

    @staticmethod
    def query_target_files(file_ids: Optional[List[int]] = None) -> List[Tuple[int, str]]:
        """获取需要挂载的文件列表 (id, name)"""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if file_ids:
                    cur.execute(
                        "SELECT id, name FROM kb.kb_file WHERE id = ANY(%s) AND delete_flag = FALSE ORDER BY id  ASC;",
                    (file_ids, ))
                else:
                    cur.execute(
                        "SELECT id, name FROM kb.kb_file WHERE delete_flag = FALSE ORDER BY id ASC;"
                    )
                return cur.fetchall()

    @staticmethod
    def insert_job_and_tasks(
            job_uuid: str,
            job_name: str,
            files: List[Tuple[int, str]]
    ) -> IngestJob:
        """单事务内创建 Job 主记录并批量挂载 Task 任务列表"""
        insert_job_sql = """
                    INSERT INTO kb.kb_ingest_job
                    (job_uuid, job_name, status, total_files, completed_files, failed_files)
                    VALUES (%s, %s, %s, %s, 0, 0)
                    RETURNING id, created_at;
                """
        insert_task_sql = """
                    INSERT INTO kb.kb_ingest_task
                    (job_id, file_id, file_name, status, attempt, max_attempts)
                    VALUES (%s, %s, %s, %s, 0, 3);
                """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(insert_job_sql, (job_uuid, job_name, JobStatus.PENDING.value, len(files)))
                job_id, created_at = cur.fetchone()

                if files:
                    task_params = [
                        (job_id, fid, fname, TaskStatus.PENDING.value)
                        for fid, fname in files
                    ]
                    execute_batch(cur, insert_task_sql, task_params, page_size=100)

                conn.commit()

        return IngestJob(
            id=job_id, job_uuid=job_uuid, job_name=job_name, status=JobStatus.PENDING,
            total_files=len(files), completed_files=0, failed_files=0, created_at=created_at
        )

    @staticmethod
    def update_job_status(job_id: int, new_status: JobStatus, set_finished: bool = False) -> bool:
        """更新作业状态（可选设置完成时间）"""
        if set_finished:
            sql = "UPDATE kb.kb_ingest_job SET status = %s, finished_at = CURRENT_TIMESTAMP WHERE id = %s;"
        else:
            sql = "UPDATE kb.kb_ingest_job SET status = %s WHERE id = %s;"

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (new_status.value, job_id))
                conn.commit()
                return cur.rowcount > 0

    @staticmethod
    def cancel_tasks_by_job_id(job_id: int):
        """将作业下挂起或未结束的任务级联置为 CANCELLED"""
        sql = """
                    UPDATE kb.kb_ingest_task
                    SET status = %s, finished_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s AND status IN (%s, %s);
                """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (TaskStatus.CANCELLED.value, job_id, TaskStatus.PENDING.value, TaskStatus.RUNNING.value)
                )
                conn.commit()

    @staticmethod
    def get_task_counts_by_status(job_id: int) -> Dict[str, int]:
        """聚合统计任务状态分布字典"""
        sql = "SELECT status, count(*) FROM kb.kb_ingest_task WHERE job_id = %s GROUP BY status;"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (job_id,))
                return dict(cur.fetchall())