# =====================================================================
# 苍穹外卖真实的 MySQL 连接配置 (请根据你本地实际账号密码修改)
# =====================================================================
import pymysql

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "Rootwyz@19951211",
    "database": "sky_take_out",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor  # 核心：以 Python 字典格式返回查询结果 (类似 Map)
}


def check_mysql_connection():
    print("=== 开始测试真实 MySQL 连接 ===")
    try:
        connection = pymysql.connect(**DB_CONFIG)
        print("✅ 成功连接到 MySQL 数据库！")

        with connection.cursor() as cursor:
            # 1. 探查当前数据库的所有表
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            print("\n📋 数据库中发现的表列表：")
            for t in tables:
                print("  •", list(t.values())[0])

                # 2. 查一下苍穹外卖真实的菜品表 (dish)
            print("\n🔍 正在查询真实菜品表 (dish) 前 3 条数据：")
            cursor.execute("SELECT id, name, price, status FROM dish LIMIT 3;")
            dishes = cursor.fetchall()
            for d in dishes:
                print(
                    f"  [ID: {d['id']}] {d['name']} - 价格: ¥{d['price']} (状态: {'在售' if d['status'] == 1 else '停售'})")

        connection.close()
    except Exception as e:
        print("❌ 连接 MySQL 失败，报错信息：", e)


if __name__ == "__main__":
    check_mysql_connection()