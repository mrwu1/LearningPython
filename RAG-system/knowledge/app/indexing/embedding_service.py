import os
import time
from typing import Optional, List

import tiktoken
from loguru import logger
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError, InternalServerError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv, find_dotenv

from app.cache.redis_cache import RedisCacheManager

load_dotenv(find_dotenv())
class EmbeddingService:
    def __init__(
            self,
            api_key:Optional[str]=None,
            base_url:Optional[str]=None,
            model_name:str = "embedding-3",
            dimensions:int = 1024,
            batch_size:int = 32,
            max_tokens_per_chunk:int = 8000
    ):
        """
        云端向量表征服务引擎
        :param model_name:向量模型，默认为："text-embedding-3-small",
        :param dimensions:向量空间维度，严格固定为：1024
        :param batch_size:单次http请求打包发送的切片数量
        :param max_tokens_per_chunk: 单切片token硬防护水位线
        """
        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.max_tokens_per_chunk = max_tokens_per_chunk
        # 初始化openai兼容客户端
        logger.info(f"OPENAI_API_KEY:{os.environ.get('OPENAI_API_KEY')}")
        resolved_api_key = api_key or os.environ.get("OPENAI_API_KEY")
        resolved_base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        if not resolved_api_key:
            logger.warning("未检测到 OPENAI_API_KEY，请确保在 .env 或初始化参数中注入。")
        self.client = OpenAI(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            timeout=30.0 #单词请求超时时间
        )
        # 初始化tokenizer
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.cache = RedisCacheManager()

    def count_token(self,text:str)->int:
        """测算文本消耗的实际 Token数量"""
        return len(self.tokenizer.encode(text))

    def _truncate_text(self,text:str)->str:
        """Token硬截断防护：超出 8191 tokens导致api抛出HTTP 400"""
        tokens = self.tokenizer.encode(text)
        if len(tokens) > self.max_tokens_per_chunk:
            logger.info(
                f"切片 Token 数 ({len(tokens)}) 超出安全限制，已防御性截断至 {self.max_tokens_per_chunk} tokens。"
            )
            return self.tokenizer.decode(tokens[:self.max_tokens_per_chunk])
        return text

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait = wait_exponential(multiplier=1,min=2,max=10),
        retry=retry_if_exception_type((RateLimitError,APITimeoutError,APIConnectionError,InternalServerError))
    )
    def _call_api_with_retry(self,batch_texts:List[str])->List[List[float]]:
        """
        执行带指数退避的底层API 批次调用 ✅✅✅
        自动对抗429限流，网络连接抖动与500/503 网关异常
        :param batch_texts:
        :return:
        """
        response = self.client.embeddings.create( # ⚠️⚠️⚠️
            model=self.model_name,
            input=batch_texts,
            dimensions=self.dimensions,
        )
        # 按照 input 的输入对齐提取 embedding 数组
        logger.info(f"✅ 本次embedding model 输出完成")
        return [item.embedding for item in response.data]

    def embed_document(self,texts:List[str])->List[List[float]]:
        """
        批量计算文档切片的向量）
        :param texts:待向量化的纯文本切片列表
        :return: 对应的1024维浮点向量列表，顺序严格一一对齐
        """
        if not texts:
            return []
        #1.前置清洗：去除异常换行并执行 Token 截断检查
        sanitized_texts = [self._truncate_text(t.replace("\r\n","\n")) for t in texts]
        logger.info(f"‼️sanitized_texts：{len(sanitized_texts)}")

        all_embeddings =[]
        total_count = len(sanitized_texts)
        logger.info(f"‼️total_count:{total_count}")
        # 2. 数组微批次切分迭代 (Micro-batching)
        for i in range(0,total_count,self.batch_size):
            batch = sanitized_texts[i:i+self.batch_size]
            start_time = time.perf_counter()
            #调用API - contain retry mechanism
            batch_vectors = self._call_api_with_retry(batch)
            all_embeddings.extend(batch_vectors)
            elapsed_time = time.perf_counter() - start_time
            logger.debug(
                f"[Embedding] 已处理批次 [{i + 1} ~ {min(i + self.batch_size, total_count)} / {total_count}] "
                f"耗时: {elapsed_time:.2f}s"
            )

        # 3. 后置防御性校验

        assert len(all_embeddings) == len(texts), (
            f"向量产出数量不匹配！预期: {len(texts)}, 实际: {len(all_embeddings)}"
        )
        if all_embeddings:
            assert len(all_embeddings[0]) == self.dimensions, (
                f"向量维度不匹配！预期: {self.dimensions}, 实际: {len(all_embeddings[0])}"
            )
        return all_embeddings
    def embedding_query(self,question:str)->List[float]:
        """
        单条查询向量化（在线问答检索使用，带 L1 Redis 缓存加速）
        :param question: 用户自然语言提问
        :return: 1024 维向量
        """
        sanitized = self._truncate_text(question.strip())
        # 1.优先查询L1 EMBEDDING CACHE
        cache_vec = self.cache.get_embedding(sanitized,self.model_name,self.dimensions)
        if cache_vec is not None:
            return cache_vec
        # 2. 未命中则调用云端 API，并将结果回写至 L1 缓存
        res = self._call_api_with_retry([sanitized])
        self.cache.set_embedding(
            sanitized,
            self.model_name,
            self.dimensions,
            vector=res[0]
        )
        return res[0]