import redis


def check_redis():
    print("=== 开始测试 Redis 连接 ===")
    try:
        # 连接本地 Redis (默认端口 6379, db 0)
        # decode_responses=True 核心参数：自动将二进制字节解码为 Python 字符串，免去 .decode('utf-8')
        r = redis.Redis(host="127.0.0.1", port=6379, db=0,password="Redis@123456" ,decode_responses=True)

        # 1. Ping 测试
        if r.ping():
            print("✅ 成功连接到 Redis！")

        # 2. 存取字符串 (带过期时间)
        r.set("agent:session:1001", "这是外卖会话历史数据", ex=60)
        val = r.get("agent:session:1001")
        print(f"📦 成功读取 Redis 缓存: {val}")

    except Exception as e:
        print("❌ 连接 Redis 失败，报错信息：", e)


if __name__ == "__main__":
    check_redis()