import sys

from loguru import logger
from contextvars import ContextVar

# 全局请求链路追踪 ContextVar，每个异步协程独立拥有自己的 trace_id
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="SYS_BOOT")


def custom_log_formatter(record: dict) -> str:
    """
    Production Log Formatter:
    Embeds current TraceID into every single log line for distributed tracing.
    """
    trace_id = trace_id_ctx.get()
    # 格式化输出：[时间] | [级别] | [TraceID] | [模块:行号] - 信息
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        f"<cyan>{trace_id}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n"
    )


def setup_logging():
    """Initializes Loguru with standard stdout sink and production formatting."""
    logger.remove()  # 移除默认 handler
    logger.add(
        sys.stdout,
        format=custom_log_formatter,
        level="INFO",
        colorize=True
    )


# 模块导入时自动初始化标准日志
setup_logging()