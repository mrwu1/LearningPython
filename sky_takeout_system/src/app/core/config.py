import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录定位
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 1. 显式加载 .env 到操作系统环境变量 os.environ 中 (LangSmith / LangChain 强制依赖 os.environ)
load_dotenv(PROJECT_ROOT / ".env", override=True)

# 2. 双向对齐 LangChain 与 LangSmith 命名兼容性
if os.environ.get("LANGSMITH_TRACING") == "true" or os.environ.get("LANGCHAIN_TRACING_V2") == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"

project_name = os.environ.get("LANGCHAIN_PROJECT") or os.environ.get("LANGSMITH_PROJECT")
if project_name:
    os.environ["LANGCHAIN_PROJECT"] = project_name
    os.environ["LANGSMITH_PROJECT"] = project_name

api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
if api_key:
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGSMITH_API_KEY"] = api_key


class Settings(BaseSettings):
    """
    loads and validates environment variables from .env file
    """
    # 1. essential service config
    ENV_MODE:Literal["dev","test" ,"prod"] = Field(
        default="dev",
        description="Environment mode",
    )
    APP_NAME:str = Field(default="SkyTakeoutSystem",description="Application name")
    APP_PORT:int = Field(default=9000, description="Application port")

    # 2. the aliyun mysql config
    DB_HOST:str = Field(...,description="Database host")
    DB_PORT:int = Field(default=3306, description="Database port")
    DB_USER:str = Field(default="root",description="Database user")
    DB_PASSWORD:str = Field(...,description="Database password")
    DB_NAME:str = Field(default="sky_take_out",description="Database name")

    # 3. the aliyun redis config
    REDIS_HOST:str = Field(...,description="Redis host")
    REDIS_PORT:int = Field(default=6379, description="Redis port")
    REDIS_PASSWORD:str = Field(default="",description="Redis password")
    REDIS_DB:int = Field(default=0,description="Redis db")

    # 4.the aliyun snopshot PostgreSQL config
    PG_HOST:str = Field(...,description="Postgres host")
    PG_PORT:int = Field(default=5432, description="Postgres port")
    PG_USER:str = Field(default="postgres",description="Postgres user")
    PG_PASSWORD:str = Field(...,description="Postgres password")
    PG_DB:str = Field(default="sky_checkpoints",description="Postgres db")

    # 5.the LLM config
    DEEPSEEK_API_KEY: SecretStr = Field(..., description="DeepSeek API Key")
    DEEPSEEK_BASE_URL: str = Field(
        default="https://api.deepseek.com",
        description="DeepSeek Base API Endpoint"
    )
    # 主力模型超时与重试保护
    PRIMARY_LLM_TIMEOUT: float = Field(default=15.0, description="主力模型超时时间(秒)")
    PRIMARY_LLM_MAX_RETRIES: int = Field(default=1, description="主力模型失败重试次数")

    # 备用容灾模型配置
    BACKUP_LLM_ENABLED: bool = Field(default=False, description="是否启用备用容灾大模型")
    BACKUP_LLM_API_KEY: SecretStr = Field(default=SecretStr(""), description="备用大模型 API Key")
    BACKUP_LLM_BASE_URL: str = Field(default="https://api.deepseek.com", description="备用模型 Base URL")
    BACKUP_LLM_MODEL: str = Field(default="deepseek-chat", description="备用模型名称")

    # 6. JWT 安全与权限配置
    JWT_SECRET_KEY: str = Field(
        default="9f82c4e1b7a6d3e8f50123456789abcdef0123456789abcdef0123456789abcdef",
        description="JWT 签名密钥"
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT 加密算法")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=120, description="Token 过期时间(分钟)")

    # 7. 全局防刷与频率限流配置 (Sliding Window Rate Limiter)
    RATE_LIMIT_USER_MAX_REQUESTS: int = Field(default=15, description="单个用户窗口期内最大请求数")
    RATE_LIMIT_USER_WINDOW_SECONDS: int = Field(default=60, description="用户限流时间窗口大小(秒)")
    RATE_LIMIT_IP_MAX_REQUESTS: int = Field(default=30, description="单个 IP 窗口期内最大请求数")
    RATE_LIMIT_IP_WINDOW_SECONDS: int = Field(default=60, description="IP 限流时间窗口大小(秒)")

    # LOAD THE .env FILE AUTOMATICALLY
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
# define a single instance for global
settings = Settings()
