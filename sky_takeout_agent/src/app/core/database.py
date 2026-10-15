from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 1. 拼接异步 MySQL 连接串：mysql+asyncmy://user:pass@host:port/dbname

DATABASE_URL = (
    f"mysql+asyncmy://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset=utf8mb4"
)

# 2. 创建企业级异步连接池引擎（对标 HikariCP）‼️

async_engine = create_async_engine(
    DATABASE_URL,
    echo=(settings.ENV_MODE == "dev"),  # 开发环境打印生成的原生 SQL，生产环境关闭
    pool_size=10,  # 核心连接池大小
    max_overflow=20,  # 突发流量允许超出的最大连接数
    pool_recycle=3600,  # 1 小时自动回收连接，防止 MySQL wait_timeout 超时断开
    pool_pre_ping=True,  # 借出连接前主动发送 PING 探活，彻底告别 gone away 报错！
)

# 3. 异步会话工厂 (对标 Java 的 EntityManagerFactory / SqlSessionFactory)
AsyncSessionLocal = async_sessionmaker(
    bind = async_engine,
    class_= AsyncSession,
    expire_on_commit=False,             # commit 后对象属性不失效，避免惰性加载抛异常
    autocommit=False,
    autoflush=False,
)
# 4. 声明式实体基类 (所有 Entity 继承自它)
class Base(DeclarativeBase):
    pass

# 5. 依赖注入生成器 (用于 FastAPI Depends，下阶段打通)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()