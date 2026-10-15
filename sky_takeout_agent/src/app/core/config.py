from pathlib import Path
from pydantic import  SecretStr
from pydantic_settings import SettingsConfigDict, BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    # 1. essential config
    ENV_MODE:str
    APP_NAME:str
    APP_PORT:int

    # 2.mysql config
    DB_HOST:str
    DB_PORT:int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # 3. 密钥类配置（使用 SecretStr 保护）
    OPENAI_API_KEY: SecretStr

    # 4. 核心：指定自动加载根目录的 .env 文件，编码为 utf-8
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

# 全局单例配置实例，业务代码直接 from app.core.config import settings
settings = Settings()