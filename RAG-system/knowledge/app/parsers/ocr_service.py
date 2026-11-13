import base64
import os
from pathlib import Path
import time
from typing import Optional
from dotenv import load_dotenv
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# 自动探测并加载根目录 .env
env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()


class ZhipuGLMOCRService:
    """
    智谱 AI 官方 GLM-OCR 大模型版面解析服务客户端 (glm-ocr)：
    官方文档: https://docs.bigmodel.cn/api-reference/模型工具/文档解析
    端点: https://open.bigmodel.cn/api/paas/v4/layout_parsing
    
    核心能力:
    1. 支持直接传入文件 URL 或 本地文件 Base64 (JPG/PNG/PDF)
    2. 深度识别复杂版面: 自动将表格还原为 Markdown 表格，保留标题与层级
    3. 直接返回高保真 Markdown 全文 (md_results)，为 RAG 提供干净输入
    4. 生产级超时与退避重试保护
    """
    def __init__(
            self,
            api_key: Optional[str] = None,
            timeout_seconds: float = 60.0,
            max_retries: int = 2,
    ):
        self.api_key = (
            api_key
            or os.getenv("ZHIPUAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ZPAI_RERANK_KEY")
        )
        if not self.api_key:
            logger.warning("[ZhipuGLMOCRService] 未检测到有效的 ZHIPUAI_API_KEY / OPENAI_API_KEY，OCR 功能调用时将受限")

        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.endpoint = "https://open.bigmodel.cn/api/paas/v4/layout_parsing"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds, connect=5.0),
            headers=headers,
        )
        logger.info(f"[ZhipuGLMOCRService] 初始化成功 | 模型: glm-ocr | 端点: {self.endpoint}")

    def _call_api_with_retry(self, payload: dict) -> dict:
        """带退避重试的 JSON POST 请求"""
        @retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1.0, min=2.0, max=5.0),
            retry=retry_if_exception_type(Exception),
        )
        def _invoke():
            resp = self.client.post(self.endpoint, json=payload)
            if resp.status_code != 200:
                logger.error(f"[ZhipuGLMOCR] 接口返回异常 (HTTP {resp.status_code}): {resp.text}")
            resp.raise_for_status()
            return resp.json()
        
        return _invoke()

    def parse_url(self, file_url: str = "", url: str = "") -> str:
        """
        通过公网可访问的 URL 直接调用 glm-ocr 进行解析 (适合 COS 托管的文件)
        :param file_url: 图片或 PDF 的公网 URL 地址 (亦可使用 url 关键字传参)
        :return: 解析后的高保真 Markdown 文本
        """
        target_url = file_url or url
        if not target_url:
            return ""

        start_time = time.perf_counter()
        payload = {
            "model": "glm-ocr",
            "file": target_url
        }

        try:
            res_json = self._call_api_with_retry(payload)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # 优先获取全局 Markdown 结果
            md_text = res_json.get("md_results", "").strip()
            
            # 若 md_results 为空，兜底从 layout_details 中拼合 content
            if not md_text and "layout_details" in res_json:
                blocks = []
                for page in res_json["layout_details"]:
                    for elem in page:
                        content = elem.get("content", "").strip()
                        if content:
                            blocks.append(content)
                md_text = "\n\n".join(blocks).strip()

            logger.info(
                f"[ZhipuGLMOCR] URL 解析成功 | 产出字符: {len(md_text)} | 耗时: {elapsed_ms:.1f}ms"
            )
            return md_text

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"[ZhipuGLMOCR] URL 解析失败 (耗时 {elapsed_ms:.1f}ms): {e}")
            raise e

    def parse_bytes(
        self,
        file_bytes: Optional[bytes] = None,
        content_bytes: Optional[bytes] = None,
        mime_type: str = "image/jpeg",
        file_name: str = "",
    ) -> str:
        """
        通过内存二进制流调用 glm-ocr 进行解析 (将字节流转为 Base64 Data URI)
        :param file_bytes: 图片或 PDF 的二进制字节流 (亦支持 content_bytes)
        :param mime_type: MIME 类型，如 image/jpeg, image/png, application/pdf
        :return: 解析后的高保真 Markdown 文本
        """
        target_bytes = file_bytes or content_bytes
        if not target_bytes:
            return ""

        # 根据文件名推断 mime_type
        if file_name:
            fn_lower = file_name.lower()
            if fn_lower.endswith(".png"):
                mime_type = "image/png"
            elif fn_lower.endswith(".pdf"):
                mime_type = "application/pdf"
            elif fn_lower.endswith(".webp"):
                mime_type = "image/webp"

        start_time = time.perf_counter()
        base64_data = base64.b64encode(target_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{base64_data}"

        payload = {
            "model": "glm-ocr",
            "file": data_uri
        }

        try:
            res_json = self._call_api_with_retry(payload)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            md_text = res_json.get("md_results", "").strip()
            logger.info(
                f"[ZhipuGLMOCR] Base64 解析成功 | 产出字符: {len(md_text)} | 耗时: {elapsed_ms:.1f}ms"
            )
            return md_text

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"[ZhipuGLMOCR] Base64 解析失败 (耗时 {elapsed_ms:.1f}ms): {e}")
            raise e


# 保持别名兼容原有引用
ZhipuOCRService = ZhipuGLMOCRService
MultimodalOCRService = ZhipuGLMOCRService
