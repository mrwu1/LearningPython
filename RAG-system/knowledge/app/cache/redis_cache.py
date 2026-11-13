import hashlib
import json
import os
from typing import Optional, List, Dict, Any

import redis
from dotenv import load_dotenv, find_dotenv
from loguru import logger
load_dotenv(find_dotenv())

class RedisCacheManager:
    """
    RAG 双层缓存与代际版本实效管理器：
    - L1: Query embedding cache
    - L2: Retrieval chunks cache (绑定 kb:corpus:version,语料变更时0（1）瞬间实效)
    - Fail-Open 容错：Redis 不可用时自动降级为无缓存直连模式
    """
    CORPUS_VERSION_KEY = "kb:corpus:version"

    def __init__(self):
        host = os.getenv("REDIS_HOST", "127.0.0.1")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD") or None
        db = int(os.getenv("REDIS_DB", "0"))
        self.client = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
    @staticmethod
    def _hash_text(text:str)->str:
        """归一化空白字符并计算 SHA256 摘要,作为 Redis Key"""
        normalized =" ".join(text.strip().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # 1. 语料库代际版本号管理 (O(1) 失效控制)
    def get_corpus_version(self)->int:
        try:
            val = self.client.get(self.CORPUS_VERSION_KEY)
            if val is None:
                self.client.set(self.CORPUS_VERSION_KEY,1)
                return 1
            return int(val)
        except Exception as e:
            logger.warning(f"[RedisCache] 读取语料版本号失败，降级使用 v1: {e}")
            return 1

    # ❌ 文件上传并解析入库完成（此时知识库变了）。
    #
    # ❌ 用户手动点击了“重建知识库索引”按钮。
    #
    # ❌ 管理员删除了某个核心文档。
    def bump_corpus_version(self)->int:
        """当知识库发生文件入库或重置时调用，使旧版L2检索全部失效"""
        try:
            new_ver = self.client.incr(self.CORPUS_VERSION_KEY)
            logger.info(f"🔄 [RedisCache] 语料库版本已跃迁至 v{new_ver}，旧版 L2 检索缓存已自动隔离失效")
            return int(new_ver)
        except Exception as e:
            logger.warning(f"[RedisCache] 递增语料版本号失败: {e}")
            return -1

    # 2. L1：Query Embedding 向量缓存

    def _build_emb_key(self,text:str,model:str,dimensions:int)->str:
        text_hash = self._hash_text(text) #32位标准字符串 作为key
        return f"kb:emb:{model}:{dimensions}:{text_hash}" #✅：返回key

    def get_embedding(self,text:str,model:str,dimensions:int)->Optional[List[float]]:
        key = self._build_emb_key(text,model,dimensions)
        try:
            raw = self.client.get(key)
            if raw:
                logger.info(f"⚡ [L1 Cache Hit] 命中查询向量缓存: '{text[:25]}'")
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"[RedisCache] L1 读取降级: {e}")
        return None

    def set_embedding(
            self,
            text:str,
            model:str,
            dimensions:int,
            vector:List[float],
            ttl_seconds:int=7*86400
    )->None:
        key = self._build_emb_key(text,model,dimensions)
        try:
            self.client.setex(key, ttl_seconds, json.dumps(vector))
        except Exception as e:
            logger.warning(f"[RedisCache] L1 写入忽略: {e}")

    # 3. L2：Retrieval 检索结果缓存 (受 corpus_version 约束)

    def _build_ret_key(self,query:str,mode:str,top_k:int)->str:
        version = self.get_corpus_version()
        query_hash = self._hash_text(query)
        return f"kb:ret:{version}:{mode}:k{top_k}:{query_hash}"

    def get_retrieval(self,query:str,mode:str,top_k:int)->List[Dict[str, Any]]|None:
        key = self._build_ret_key(query,mode,top_k)
        try:
            raw = self.client.get(key)
            if raw:
                logger.info(f"⚡ [L2 Cache Hit] 命中检索缓存 (v={self.get_corpus_version()}, mode={mode},top_k = {top_k})")
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"[RedisCache] L2 读取降级: {e}")
        return None

    def set_retrieval(
            self,
            query:str,
            mode:str,
            top_k:int,
            chunks_data:List[Dict[str, Any]]|None,
            ttl_seconds:int=3600
    )->None:
        key = self._build_ret_key(query,mode,top_k)
        try:
            self.client.setex(key, ttl_seconds, json.dumps(chunks_data, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[RedisCache] L2 写入忽略: {e}")