"""
    统一数据库连接池基础设施模块 (Database Connection Infrastructure)
    全局单例连接池，提供线程安全的连接借还上下文、异常事务自动回滚与 pgvector 类型注册。
    """
import os
import logging
from typing import Optional, Set
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
logger = logging.getLogger(__name__)


class DatabasePool:
    """
    PostgreSQL 全局单例连接池管理器
    """
    _pool: Optional[pool.ThreadedConnectionPool] = None
    _registered_conn_ids: Set[int] = set()

    @classmethod
    def get_pool(cls) -> pool.ThreadedConnectionPool:
        """获取或懒加载初始化全局单例连接池"""
        if cls._pool is None:
            minconn = int(os.getenv("PG_MIN_CONN", 2))
            maxconn = int(os.getenv("PG_MAX_CONN", 20))
            host = os.getenv("PG_HOST", "localhost")
            port = int(os.getenv("PG_PORT", 5432))
            dbname = os.getenv("PG_DB", "rag_db")
            user = os.getenv("PG_USER", "postgres")
            password = os.getenv("PG_PASSWORD", "postgres")

            try:
                cls._pool = pool.ThreadedConnectionPool(
                    minconn=minconn,
                    maxconn=maxconn,
                    host=host,
                    port=port,
                    dbname=dbname,
                    user=user,
                    password=password,
                )
                logger.info(
                    f"[DatabasePool] 全局单例连接池初始化成功 (min={minconn}, max={maxconn}, db={dbname})"
                )
            except Exception as e:
                logger.error(f"[DatabasePool] 初始化数据库连接池异常: {e}")
                raise e
        return cls._pool

    @classmethod
    def close_all(cls):
        """平滑关闭整个连接池（用于应用退出时销毁资源）"""
        if cls._pool is not None:
            cls._pool.closeall()
            cls._pool = None
            cls._registered_conn_ids.clear()
            logger.info("[DatabasePool] 全局数据库连接池已安全关闭")


@contextmanager
def get_db_connection():
    """
    生产级数据库连接借还上下文管理器 (Context Manager)
    使用方法：
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    保证：
        1. 自动对物理连接注册 pgvector 类型（带 OID 缓存，不重复查系统表）
        2. 发生任何 SQL/业务异常时自动 rollback 回滚事务，避免污染连接池
        3. 无论正常退出还是抛出异常，finally 阶段均执行 rollback 并安全归还连接池
    """
    p = DatabasePool.get_pool()
    conn = p.getconn()
    try:
        conn_id = id(conn)
        if conn_id not in DatabasePool._registered_conn_ids:
            try:
                register_vector(conn)
                DatabasePool._registered_conn_ids.add(conn_id)
            except Exception as reg_err:
                logger.warning(f"[DatabasePool] 注册 pgvector 类型失败 (非致命): {reg_err}")

        yield conn

    except Exception as e:
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.warning(f"[DatabasePool] 异常回滚失败: {rb_err}")
        logger.error(f"[DatabasePool] 数据库执行遇到异常，事务已回滚: {e}")
        raise e

    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        p.putconn(conn)