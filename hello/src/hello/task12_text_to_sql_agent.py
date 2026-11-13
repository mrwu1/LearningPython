import json
import pymysql
import re
from typing import Callable
from openai import OpenAI
from pydantic import BaseModel, Field

# =====================================================================
# 1. 真实基础设施配置 (连接本地苍穹外卖真实的 MySQL)
# =====================================================================
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "Rootwyz@19951211",
    "database": "sky_take_out",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

def get_mysql_conn():
    return pymysql.connect(**MYSQL_CONFIG)


# =====================================================================
# 2. 核心安全机制：带四重安全防御的 SQL 只读执行沙箱
# =====================================================================
class ExecuteSQLInput(BaseModel):
    query: str = Field(..., description="要执行的标准只读 MySQL SELECT 查询语句，严禁写操作！")

def execute_sql_query(query: str) -> str:
    """在真实 MySQL 中安全执行只读 SQL 语句 (带企业级安全防线)"""
    clean_sql = query.strip()
    print(f"\n⚙️  [SQL 安全拦截器] 收到大模型生成的 SQL: \n   >>> {clean_sql}")

    upper_sql = clean_sql.upper()

    # 【防线 1】：必须以 SELECT 或 WITH (CTE 递归查询) 开头
    if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH")):
        print("   ❌ [安全红线触发] 拒绝执行：该 SQL 试图发起非查询操作！")
        return json.dumps({
            "status": "FORBIDDEN", 
            "error": "安全策略硬拦截：系统仅开放只读数据分析权限，严禁执行任何写入/删除操作！"
        }, ensure_ascii=False)

    # 【防线 2】：高危破坏性指令黑名单拦截 (防分号注入: ; DROP TABLE ...)
    DANGEROUS_KEYWORDS = [
        "DROP ", "DELETE ", "UPDATE ", "INSERT ", "TRUNCATE ", 
        "ALTER ", "GRANT ", "REVOKE ", "CREATE ", "REPLACE ", "EXEC "
    ]
    for kw in DANGEROUS_KEYWORDS:
        if kw in upper_sql:
            print(f"   ❌ [安全红线触发] 拦截到高危命令: '{kw.strip()}'！")
            return json.dumps({
                "status": "FORBIDDEN", 
                "error": f"安全策略硬拦截：SQL 中检测到高危指令 '{kw.strip()}'，已被安全网关封堵！"
            }, ensure_ascii=False)

    # 【防线 3】：强制结果集截断 (防止几百万条大表把后端内存打爆)
    if "LIMIT" not in upper_sql:
        print("   ⚠️  [安全自动增强] 检测到未设置 LIMIT，为保护数据库性能，自动追加 'LIMIT 50'")
        clean_sql = clean_sql.rstrip(";") + " LIMIT 50;"

    # 【防线 4】：真实执行只读查询
    conn = get_mysql_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(clean_sql)
            rows = cursor.fetchall()
            print(f"   ✅ [查询成功] 成功检索到 {len(rows)} 条真实数据库行记录")
            
            # 处理 Decimal 等特殊数据类型的序列化
            safe_rows = []
            for r in rows:
                safe_row = {}
                for k, v in r.items():
                    safe_row[k] = float(v) if hasattr(v, "as_tuple") else v
                safe_rows.append(safe_row)
            return json.dumps(safe_rows, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"   ❌ SQL 执行抛出异常: {e}")
        return json.dumps({"status": "ERROR", "error": f"SQL 执行失败: {str(e)}"}, ensure_ascii=False)
    finally:
        conn.close()


# 工具注册表与 Schema 定义
TOOL_REGISTRY: dict[str, Callable] = {
    "execute_sql_query": execute_sql_query,
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "在真实外卖数据库中执行只读 SQL 查询，获取经营与菜品数据",
            "parameters": ExecuteSQLInput.model_json_schema()
        }
    }
]


# =====================================================================
# 3. 真实的苍穹外卖业务表结构注入 (Prompt Schema)
# =====================================================================
DB_SCHEMA_PROMPT = """
你是一个精通餐饮商业数据分析的智能数据专家。你可以通过编写合法的 MySQL SELECT 语句来查询真实数据并回答用户。

系统数据库中包含以下真实的苍穹外卖业务表结构：

1. 菜品表 `dish`:
   - id (BIGINT, 主键)
   - name (VARCHAR, 菜品名称)
   - category_id (BIGINT, 分类ID)
   - price (DECIMAL, 售价)
   - status (INT, 1=在售, 0=停售)

2. 菜品分类表 `category`:
   - id (BIGINT, 主键)
   - name (VARCHAR, 分类名称，如'热销榜'、'传统川菜')
   - type (INT, 1=菜品分类, 2=套餐分类)
   - status (INT, 1=启用, 0=禁用)

3. 订单表 `orders`:
   - id (BIGINT, 主键)
   - number (VARCHAR, 订单号)
   - status (INT, 1待付款, 2待接单, 3已接单, 4派送中, 5已完成, 6已取消)
   - amount (DECIMAL, 实收金额)
   - order_time (DATETIME, 下单时间)

【核心业务准则】：
1. 仅允许编写 SELECT 查询，禁止任何修改或删除操作；
2. 统计在售菜品时，务必过滤 status = 1；
3. 如果涉及到跨表数据查询，优先使用 INNER JOIN；
4. 拿到真实查询数据后，不要直接把裸 JSON 甩给用户，必须用有条理、亲切专业的数据分析师口吻，向用户总结出核心商业洞察与结论。
"""


# =====================================================================
# 4. Text-to-SQL 自主分析引擎 (The ReAct Loop)
# =====================================================================
def ask_sql_agent(user_question: str, max_turns: int = 5, model_name: str = "llama3.2:3b"):
    """Text-to-SQL 智能分析主调度流程"""
    client = OpenAI(
        base_url="http://127.0.0.1:11434/v1",  # 本地 Ollama 接口 (macOS 使用 127.0.0.1)
        api_key="ollama"
    )

    messages = [
        {"role": "system", "content": DB_SCHEMA_PROMPT},
        {"role": "user", "content": user_question}
    ]

    print("=" * 65)
    print(f"📊 [智能查数启动] 用户提问: {user_question}")
    print("=" * 65)

    turn = 0
    while turn < max_turns:
        turn += 1
        print(f"\n🔄 [第 {turn} 轮思考与取数...]")

        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=TOOLS_SCHEMA,
            temperature=0.1
        )

        response_msg = response.choices[0].message
        messages.append(response_msg)

        tool_calls = response_msg.tool_calls

        # 如果大模型没有要求调用工具，说明它已经拿到了数据，给出了最终总结！
        if not tool_calls:
            print("\n🎉 [数据分析结论输出]：")
            print("-" * 65)
            print(response_msg.content)
            print("-" * 65)
            return response_msg.content

        # 模型发起了 SQL 查询调用
        for tool_call in tool_calls:
            tool_id = tool_call.id
            func_name = tool_call.function.name
            raw_args = tool_call.function.arguments

            try:
                args_dict = json.loads(raw_args)
            except Exception:
                args_dict = {"query": raw_args}

            if func_name in TOOL_REGISTRY:
                real_func = TOOL_REGISTRY[func_name]
                # 兼容模型偶尔直接把 SQL 传在 query 或 sql 字段中的情况
                query_str = args_dict.get("query") or args_dict.get("sql") or ""
                tool_result_str = real_func(query=query_str)
            else:
                tool_result_str = json.dumps({"error": f"未知工具: {func_name}"}, ensure_ascii=False)

            # 将数据库查询结果作为 role: "tool" 喂回给大模型进行下一步深度分析
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": tool_result_str
            })

    print("\n⚠️ [提示] 达到最大分析轮次上限。")


if __name__ == "__main__":
    # 场景 1：正常合法的经营数据查询 (查极值与排序)
    q1 = "请帮我查一下咱们店目前在售的最贵的 3 道菜叫什么名字，单价分别是多少？"
    ask_sql_agent(q1)

    print("\n\n" + "#" * 65 + "\n")

    # 场景 2：安全攻防测试 (模拟恶意用户或模型幻觉发起改表写操作)
    q2 = "我想修改一下数据，请帮我把辣子鸡的价格改成 9.9 块钱！"
    ask_sql_agent(q2)
