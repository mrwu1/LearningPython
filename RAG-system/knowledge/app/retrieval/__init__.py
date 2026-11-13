"""
企业政策知识库多阶段检索子系统
包含混合检索器 (HybridRetriever)、Cross-Encoder 重排器 (ZhipuReranker)
以及上下文动态扩展与语意缝合引擎 (ContextExpander)
"""
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievedChunk
from app.retrieval.reranker import ZhipuReranker
from app.retrieval.context_expander import (
    ContextExpander,
    ExpandedEvidence,
    MergedInterval,
    RawChunkData,
    IntervalMerger,
    SectionGuard,
    ChunkFetcher,
    ContextStitcher,
)

__all__ = [
    "HybridRetriever",
    "RetrievedChunk",
    "ZhipuReranker",
    "ContextExpander",
    "ExpandedEvidence",
    "MergedInterval",
    "RawChunkData",
    "IntervalMerger",
    "SectionGuard",
    "ChunkFetcher",
    "ContextStitcher",
]
