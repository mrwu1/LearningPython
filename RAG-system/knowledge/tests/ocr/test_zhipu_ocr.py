import json
import os
import sys
from pathlib import Path
import httpx
from dotenv import load_dotenv, find_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(find_dotenv())

from app.parsers.ocr_service import ZhipuOCRService
import psycopg2


def run_ocr_test():
    print("=" * 80)
    print("🚀 开始验证 Module 2.3：智谱官方工具 API - OCR 图片识别服务")
    print("=" * 80)

    # 1. 实例化 OCR 服务
    ocr_service = ZhipuOCRService()

    # 2. 从数据库中寻找一张真实的制度图片（.jpg 或 .png）
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "127.0.0.1"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "knowledge"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "postgres"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                    SELECT id, name, url, file_ext
                    FROM kb.kb_file
                    WHERE delete_flag = FALSE AND file_ext IN ('.jpg', '.png', 'jpg', 'png')
                    ORDER BY id ASC
                    LIMIT 1;
                """)
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        print("❌ 未在数据库中检索到图片文件！")
        return

    file_id, file_name, file_url, file_ext = row
    print(f"\n[测试样本] ID: {file_id} | 文件名: {file_name}")
    print(f"[下载地址] {file_url[:60]}...")

    # 3. 下载真实图片二进制流
    print("\n[步骤 1] 正在下载图片流...")
    resp = httpx.get(file_url, timeout=15.0)
    assert resp.status_code == 200, f"图片下载失败，HTTP 状态码: {resp.status_code}"
    image_bytes = resp.content
    print(f"👉 下载成功，图片大小: {len(image_bytes)} bytes")

    # 4. 调用智谱官方 OCR 服务识别
    print("\n[步骤 2] 发送至智谱官方 /files/ocr 端点识别...")
    extracted_text = ocr_service.parse_image_bytes(
        image_bytes=image_bytes,
        file_name=file_name,
        language_type="CHN_ENG"
    )

    print("\n" + "=" * 80)
    print("📋 智谱 OCR 识别提取出的真实文本内容 (前 500 字符展示):")
    print("-" * 80)
    print(extracted_text[:500] if extracted_text else "(未识别到文字)")
    print("=" * 80)

    # 5. 断言验证
    assert len(extracted_text.strip()) > 0, "❌ 识别失败：未提取出任何文字！"
    print(f"\n✅ 测试通过！成功识别提取 {len(extracted_text)} 个字符。智谱官方 OCR 工具服务对接成功！")


if __name__ == "__main__":
    run_ocr_test()