from typing import AsyncGenerator

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 1. 安全构造 MySQL 异步连接串 (自动对特殊字符转义，防止密码中的 @ 截断 URL)
MYSQL_DATABASE_URL = URL.create(
        drivername="mysql+asyncmy",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
        query={"charset": "utf8mb4"}
)
# 2. 创建企业级异步连接池引擎 (对标 Java HikariCP)
async_engine = create_async_engine(
    MYSQL_DATABASE_URL,
    echo=(settings.ENV_MODE == "dev"),  # 开发环境打印 SQL，生产环境关闭
    pool_size=10,  # 核心连接池大小
    max_overflow=20,  # 突发流量允许超出的最大连接数
    pool_recycle=3600,  # 1 小时自动回收连接，防止 MySQL 8 小时 wait_timeout 断开
    pool_pre_ping=True,  # 每次借出连接前主动 ping 探活，彻底告别 2006 gone away 错误
)
# 3. 异步会话工厂 (Session Factory)
AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,             # 提交后属性不失效，避免异步惰性加载抛异常
        autocommit=False,
)


# 4. ORM 声明式模型基类 (后续所有 Model 实体继承它)
class Base(DeclarativeBase):
    pass

# 5. FastAPI 依赖注入生成器 (用于 API 路由中注入 Session)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()