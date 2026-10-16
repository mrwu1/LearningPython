import redis.asyncio
from loguru import logger

from app.core.config import settings

# 1.create a global async redis connect pool
redis_pool = redis.asyncio.ConnectionPool(
    host = settings.REDIS_HOST,
    port = settings.REDIS_PORT,
    password = settings.REDIS_PASSWORD,
    db = settings.REDIS_DB,
    #核心：自动把字节流解码为 Python str，免去手动 .decode("utf-8")
    # decode_response = settings.DECORD_RESPONSE,
    protocol=2,               # 兼容 RESP2，杜绝远程代理握手假死
    socket_timeout=10,         # 网络超时保底
    decode_responses=True,     # 关键：连接池自动解码为 Python str                                                           max_connections=settings.MAX_CONNECTIONS
)
logger.info(f"redis pool config:{redis_pool}")
# 2. get the instance of the redis client:
redis_client = redis.asyncio.Redis(connection_pool=redis_pool,
                                   decode_responses=settings.DECORD_RESPONSE)

