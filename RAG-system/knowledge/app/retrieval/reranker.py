import os
import time
from typing import Optional, List
from loguru import logger

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

class ZhipuReranker:
    def __init__(
        self,
        api_key:Optional[str] = None,
        model:str = 'rerank',
        base_url: Optional[str] = None,
        timeout_seconds:int = 8,
        max_retries: int = 2,
    ):
        """
                智谱 AI 生产级 Cross-Encoder 重排器 (rerank-1)：
                1. 全自注意力计算 Query 与候选 Document 的深度语义交互匹配分
                2. 指数退避重试 (tenacity)
                3. 支持传入文本列表，返回按相关性降序排列的 (index, score) 列表
        """
        self.api_key = api_key or os.getenv("ZPAI_RERANK_KEY")
        if not self.api_key:
            raise ValueError("[ZhipuReranker] 未检测到有效的  ZPAI_RERANK_KEY 环境变量！")

        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        # 核心生产改造：显式构建带超时的 httpx 客户端，并关闭 SDK 隐式重试（由外层 tenacity 统一管理）
        self.endpoint = self.base_url.rstrip("/") + "/rerank"
        # 复用长连接客户端
        self.client = httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds, connect=3.0),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        logger.info(
            f"[ZhipuReranker] 初始化成功 | 模型: {self.model} | "
            f"端点: {self.endpoint} | 超时: {self.timeout_seconds}s | 重试上限: {self.max_retries}"
        )

        # 动态使用 self.max_retries 限制外层重试
    def _call_api_with_retry(self, query: str, documents: List[str], top_n: int):
        """调用智谱重排接口（带受控指数退避）"""
        @retry(
                reraise=True,
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=0.5, min=1.0, max=3.0),
                retry=retry_if_exception_type(Exception),
        )
        def _invoke():
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": False
            }
            resp = self.client.post(self.endpoint, json=payload)
            resp.raise_for_status()
            return resp.json()
        return _invoke()

    def rerank(
                self,
                query: str,
                documents: List[str],
                top_n: Optional[int] = None
    ) -> List[dict]:
            """
            对传入的候选文本列表进行深度语义重排。
            """
            if not documents:
                return []

            top_n = top_n or len(documents)
            start_time = time.perf_counter()

            try:
                data = self._call_api_with_retry(query=query, documents=documents, top_n=top_n)
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                raw_results = data.get("results", [])
                end_results = []
                # 解析 第三方返回的结果：
                # {
                #     "id": "20241120141244890ab4ee4af84acf",
                #     "results": [
                #         {
                #             "document": "Washington, D.C. is the capital of the United States.",
                #             "index": 1,
                #             "relevance_score": 0.99866986
                #         }
                #     ],
                #     "usage": {
                #         "prompt_tokens": 72,
                #         "total_tokens": 72
                #     },
                #     "created": 1732083164,
                #     "request_id": "1111111111"
                # }
                for item in raw_results:
                    end_results.append({
                        "index": int(item["index"]),
    			        "relevance_score": float(item["relevance_score"])
                    })
                logger.info(
                    f"[ZhipuReranker] 重排完成 | 候选数: {len(documents)} -> 截取 Top-{len(end_results)} | "
                    f"耗时: {elapsed_ms:.2f}ms"
                )
                return end_results
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.error(f"[ZhipuReranker] 调用失败 (耗时 {elapsed_ms:.2f}ms): {e}")

                raise e