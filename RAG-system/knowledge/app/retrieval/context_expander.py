"""
动态上下文扩展与语意缝合引擎门面 (Context Expander Facade)
采用 Small-to-Big 检索范式，在重排后自动将孤立的核心切片向外智能补全前后文。
经组件化拆分，本门面统一协调：
1. IntervalMerger: 区间连通性探测与重叠合并
2. ChunkFetcher: 单次批量 SQL 批量拉取 (零 N+1)
3. SectionGuard: 大章节 (Heading Path) 与工作表 (Sheet Name) 硬隔离
4. ContextStitcher: 文本有序缝合与上下文预算熔断
"""
import logging
from typing import List, Dict, Any, Optional

from app.retrieval.hybrid_retriever import RetrievedChunk
from app.retrieval.expansion.models import ExpandedEvidence, MergedInterval, RawChunkData
from app.retrieval.expansion.interval_merger import IntervalMerger
from app.retrieval.expansion.chunk_fetcher import ChunkFetcher
from app.retrieval.expansion.section_guard import SectionGuard
from app.retrieval.expansion.context_stitcher import ContextStitcher

logger = logging.getLogger(__name__)

__all__ = [
    "ExpandedEvidence",
    "MergedInterval",
    "RawChunkData",
    "IntervalMerger",
    "ChunkFetcher",
    "SectionGuard",
    "ContextStitcher",
    "ContextExpander",
]


class ContextExpander:
    """
    上下文动态扩展与语意缝合引擎门面类
    """
    def __init__(
        self,
        window_size: int = 1,
        max_total_chars: int = 4000,
        chunk_fetcher: Optional[ChunkFetcher] = None,
    ):
        """
        :param window_size: 邻近切片扩展窗口 (默认 1，即向前拉取 1 个，向后拉取 1 个)
        :param max_total_chars: 送入大模型证据上下文的总字数硬预算熔断阈值 (默认 4000)
        :param chunk_fetcher: 可选的自定义数据抓取器 (支持外部注入以复用连接池或 Mock 测试)
        """
        self.window_size = window_size
        self.max_total_chars = max_total_chars
        self.merger = IntervalMerger(window_size=window_size)
        self.fetcher = chunk_fetcher or ChunkFetcher()
        self.stitcher = ContextStitcher(max_total_chars=max_total_chars)

    def expand_chunks(
        self,
        candidates: List[RetrievedChunk],
        enable_expansion: bool = True,
    ) -> List[ExpandedEvidence]:
        """
        核心调度入口：对重排召回的 Top-k 候选切片执行区间合并、单次批量 SQL 抓取与大章节硬隔离缝合
        :param candidates: 粗排或精排后的候选切片列表 (RetrievedChunk)
        :param enable_expansion: 是否开启上下文扩展 (默认 True)
        :return: 扩展并缝合后的高语义完整度证据列表 (ExpandedEvidence)
        """
        if not candidates:
            return []

        # 开关控制：若未启用扩展或窗口为 0，直接封装为原子证据返回，杜绝多余开销
        if not enable_expansion or self.window_size <= 0:
            return [
                ExpandedEvidence(
                    evidence_id=f"E{idx + 1}",
                    file_id=c.file_id,
                    file_name=c.file_name,
                    primary_chunk_index=c.chunk_index,
                    expanded_indices=[c.chunk_index],
                    heading_path=c.metadata.get("heading_path"),
                    page_no=c.metadata.get("page_no"),
                    sheet_name=c.metadata.get("sheet_name"),
                    score=c.score,
                    rerank_score=c.rerank_score,
                    content=c.content,
                    is_expanded=False,
                )
                for idx, c in enumerate(candidates)
            ]

        # 1. 按文件分组 (只对同一份文件内的切片执行区间连通性探测)
        file_candidates: Dict[int, List[RetrievedChunk]] = {}
        for c in candidates:
            file_candidates.setdefault(c.file_id, []).append(c)

        expanded_results: List[ExpandedEvidence] = []
        evidence_counter = 1
        remaining_budget = self.max_total_chars

        for file_id, file_chunks in file_candidates.items():
            if remaining_budget <= 0:
                logger.warning(f"[ContextExpander] 达到总字数预算上限 ({self.max_total_chars})，"
                               f"提前截断后续文件扩展")
                break

            # 2. 调用 IntervalMerger 计算闭区间并执行重叠/相邻合并
            merged_intervals = self.merger.merge_candidate_intervals(file_chunks)

            # 3. 收集该文件所有区间需要抓取的切片序号，单次批量 SQL 抓取 (杜绝 N+1 查询)
            all_target_indices: List[int] = []
            for interval in merged_intervals:
                all_target_indices.extend(interval.target_indices)

            chunk_map = self.fetcher.fetch_chunks(file_id, all_target_indices)

            # 4. 逐个区间执行边界校验 (SectionGuard)、正文有序缝合与预算控制 (ContextStitcher)
            for interval in merged_intervals:
                if remaining_budget <= 0:
                    break

                stitch_result = self.stitcher.stitch_interval(
                    interval=interval,
                    chunk_map=chunk_map,
                    evidence_index=evidence_counter,
                    remaining_chars_budget=remaining_budget,
                )

                if stitch_result:
                    evidence, consumed = stitch_result
                    expanded_results.append(evidence)
                    evidence_counter += 1
                    remaining_budget -= consumed

        # 5. 保持整体优先级排序 (按重排分优先，原检索分次优倒序)
        expanded_results.sort(
            key=lambda x: (
                x.rerank_score if x.rerank_score is not None else -1.0,
                x.score
            ),
            reverse=True
        )

        # 重新规整 evidence_id 为 E1, E2, ...
        for idx, ev in enumerate(expanded_results):
            ev.evidence_id = f"E{idx + 1}"

        return expanded_results
