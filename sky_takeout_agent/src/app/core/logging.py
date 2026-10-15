import sys
from contextvars import ContextVar
from pathlib import Path
from loguru import logger

# 1. 协程上下文变量 (对标 Java MDC)
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="SYSTEM")


def trace_id_patcher(record: dict) -> None:
    """自动给每一条日志的 extra 注入 trace_id"""
    record["extra"]["trace_id"] = trace_id_ctx.get()


def setup_logging():
    """顶格定义的全局日志初始化函数"""
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>[TraceID: {extra[trace_id]}]</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    # 1. 终端彩色输出
    logger.add(sys.stdout, format=log_format, level="INFO")

    # 2. 磁盘文件异步滚动落盘 (固定在项目根目录的 logs 下)
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        str(log_dir / "app.log"),
        format=log_format,
        level="INFO",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        enqueue=True,
        encoding="utf-8"
    )

    # 🌟 核心：使用 configure(patcher=...) 让 patcher 全局生效
    logger.configure(patcher=trace_id_patcher)
    return logger


# 全局单例初始化
setup_logging()