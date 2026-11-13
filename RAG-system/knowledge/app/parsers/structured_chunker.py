import re
from typing import Dict, Any, List
import jieba
from loguru import logger
# 1. 数据结构定义（StructuredBlock 与 DocumentChunk）
# 2. 标题探索与状态机（_detect_heading + segment_info_blocks)
# 3. 按照边界聚拢 装箱
from pydantic import BaseModel, Field

class StructuredBlock(BaseModel):
    """原子语义积木"""
    block_type: str # heading , paragraph,table, excel_row
    heading_path:str # 继承的祖先章节路径 ，如 "第一章 财务制度 > 1.1 差旅标准"
    page_no: int|None= None # PDF/PPTX 页码
    sheet_name:str|None= None # Excel 表单名
    row_range:str|None= None   # Excel 行号坐标
    text:str  #正文文本

class DocumentChunk(BaseModel):
    """最终存盘向量切片（输出实体）"""
    chunk_index:int  # 切片序号: 0, 1, 2...
    content:str # 注入【制度来源】+【章节定位】后的最终完整文本
    token_count:int # 字符预估数
    jieba_tokens:str # 供 PG GIN 倒排索引检索的分词串
    metadata:Dict[str,Any] # 包含 page_no, heading_path, prev/next 指针等

class StructuredChunker:
    """
    智能边界结构化切片引擎
    """
    # 中英文法规规章典型标题与条款正则模式
    HEADING_PATTERNS = [
        # 中文传统章节法条
        re.compile(r"^(第[一二三四五六七八九十百]+[编章节部篇])\s*(.*)$"),
        re.compile(r"^(第[一二三四五六七八九十百0-9]+条)\s*(.*)$"),
        re.compile(r"^([一二三四五六七八九十]+、)\s*(.*)$"),
        re.compile(r"^(\([一二三四五六七八九十]+\))\s*(.*)$"),
        # 英文法条 (Chapter 1, Section 2.1, Article 4, Appendix A 等)
        re.compile(r"^(Chapter|Part|Section|Article|Policy|Appendix)\s+([0-9IVXLCDMivxlcdm]+|[A-Z])[:\.\s]\s*(.*)$",
                   re.IGNORECASE),
        # 通用数字层级 (1.1, 1.1.2) 与 Markdown
        re.compile(r"^(\d+(\.\d+)+)\s+(.*)$"),
        re.compile(r"^(\d+)\.\s+([A-Z\u4e00-\u9fa5].*)$"),
        re.compile(r"^(#{1,4})\s+(.*)$"),
    ]
    PAGE_PATTERN = re.compile(r"^\[第(\d+)页(?:幻灯片)?\]") # pdf
    EXCEL_ROW_PATTERN = re.compile(r"^【表单:\s*([^,]+),\s*第(\d+)行】") #excel

    def __init__(self, target_chunk_size: int = 500, chunk_overlap: int = 100) -> None:
        self.chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap
        jieba.initialize()

    def _detect_heading(self, line: str) -> str | None:
        """探索当前行是否为标题（含：长度熔断，标点熔断和全大写检测）"""
        clean_line = line.strip()
        # ‼️规则1:长度超过60或者带句号分号结尾的，坚决不是标题
        if len(clean_line) > 60 or clean_line.endswith(("。", "；", ";", ".")):
            return None
        # ‼️规则2:探测英文全大写标题行
        if clean_line.isupper() and 4 <= len(clean_line) <= 50:
            return clean_line   # ‼️规则3:正则探测：
        for pattern in self.HEADING_PATTERNS:
            if pattern.match(clean_line):
                return clean_line

        return None

    def segment_into_blocks(self, raw_lines: List[str]) -> List[StructuredBlock]:
        """将原始文本行流切分为保留坐标的语义积木 (积木生成阶段)"""
        blocks: List[StructuredBlock] = []
        heading_stack: List[str] = []
        current_page: int | None = None
        current_sheet: str | None = None

        for line in raw_lines:
            text = line.strip()
            if not text:
                continue

            row_range = None

            # 1. 探测 PDF/PPTX 页码标头
            page_match = self.PAGE_PATTERN.match(text)
            if page_match:
                current_page = int(page_match.group(1))

            # 2. 探测 excel 工作表标头
            excel_match = self.EXCEL_ROW_PATTERN.match(text)
            if excel_match:
                current_sheet = excel_match.group(1).strip()
                row_range = excel_match.group(2).strip()

            # 3. 探测标题并维护标题栈
            heading = self._detect_heading(text)
            if heading:
                # 判定是否属于大章节 (中英文)
                h_lower = heading.lower()
                is_top = (any(k in heading for k in ["章", "编", "部", "一、", "二、", "三、"]) or
                          any(h_lower.startswith(k) for k in ["chapter", "part", "policy"]))
                if is_top:
                    heading_stack = [heading]
                elif len(heading_stack) >= 3:
                    heading_stack[-1] = heading
                else:
                    heading_stack.append(heading)

                blocks.append(StructuredBlock(
                    block_type="heading",
                    heading_path=" > ".join(heading_stack),
                    page_no=current_page,
                    sheet_name=current_sheet,
                    row_range=row_range,
                    text=text,
                ))
                continue
            # 4. 普通正文或表格积木
            is_table = text.startswith("|") and text.endswith("|")
            b_type = "table" if is_table else ("excel_row" if current_sheet else "paragraph")
            blocks.append(
                StructuredBlock(
                    block_type=b_type,
                    heading_path=" > ".join(heading_stack) if heading_stack else "",
                    page_no=current_page,
                    sheet_name=current_sheet,
                    row_range=row_range,
                    text=text,
                )
            )
        return blocks

    def build_chunks(
            self,
            blocks:List[StructuredBlock],
            file_id:int|str,
            file_name:str,
            file_ext:str
    )->List[DocumentChunk]: #‼️
        """将积木智能聚合成最终切片，并注入前后双向链表指针 (装箱封箱阶段)"""
        raw_chunks: List[Dict[str, Any]] = []
        current_texts: List[str] = []
        current_len = 0
        current_meta = {
            "page_no": None,
            "heading_path": "",
            "sheet_name": None,
            "row_range": None,
        }

        def flush_current():
            nonlocal current_texts, current_len, current_meta
            if not current_texts:
                return
            combined_text = "\n\n".join(current_texts).strip()
            if combined_text:
                raw_chunks.append({
                    "text": combined_text,
                    "page_no": current_meta["page_no"],
                    "heading_path": current_meta["heading_path"],
                    "sheet_name": current_meta["sheet_name"],
                    "row_range": current_meta["row_range"],
                })
            current_texts = []
            current_len = 0

        for block in blocks:
            b_len = len(block.text)

            if not current_texts:
                current_meta = {
                    "page_no": block.page_no,
                    "heading_path": block.heading_path,
                    "sheet_name": block.sheet_name,
                    "row_range": block.row_range,
                }

            # 三大约束断开条件：换页、换大章、容量溢出
            page_changed = block.page_no and current_meta["page_no"] and block.page_no != current_meta["page_no"]
            heading_changed = (block.block_type == "heading" and current_len > (self.chunk_size // 3))

            if page_changed or heading_changed or (current_len + b_len > self.chunk_size):
                flush_current()
                current_meta = {
                    "page_no": block.page_no,
                    "heading_path": block.heading_path,
                    "sheet_name": block.sheet_name,
                    "row_range": block.row_range,
                }

            # 单块自身超长截断处理
            if b_len > self.chunk_size:
                sub_parts = self._split_large_block(block.text)
                for part in sub_parts:
                    raw_chunks.append({
                        "text": part,
                        "page_no": block.page_no,
                        "heading_path": block.heading_path,
                        "sheet_name": block.sheet_name,
                        "row_range": block.row_range,
                    })
            else:
                current_texts.append(block.text)
                current_len += b_len

        flush_current()

        # 生成带有【制度来源】+【章节/页码定位】与【前后指针】的最终切片
        total_chunks = len(raw_chunks)
        final_chunks: List[DocumentChunk] = []

        for idx, item in enumerate(raw_chunks):
            header_parts = [f"【制度来源：{file_name}】"]
            if item["heading_path"]:
                header_parts.append(f"【章节：{item['heading_path']}】")
            elif item["page_no"]:
                header_parts.append(f"【定位：第 {item['page_no']} 页】")
            elif item["sheet_name"]:
                header_parts.append(f"【工作表：{item['sheet_name']}】")

            enriched_content = "\n".join(header_parts) + f"\n{item['text']}"

            cut_words = jieba.cut_for_search(enriched_content)
            jieba_tokens = " ".join([w.strip() for w in cut_words if w.strip()])

            chunk_meta = {
                "file_id": file_id,
                "file_name": file_name,
                "file_ext": file_ext,
                "chunk_index": idx,
                "page_no": item["page_no"],
                "heading_path": item["heading_path"],
                "sheet_name": item["sheet_name"],
                "row_range": item["row_range"],
                # 双向链表指针
                "prev_chunk_index": idx - 1 if idx > 0 else None,
                "next_chunk_index": idx + 1 if idx < total_chunks - 1 else None,
            }

            final_chunks.append(
                DocumentChunk(
                    chunk_index=idx,
                    content=enriched_content,
                    token_count=len(enriched_content),
                    jieba_tokens=jieba_tokens,
                    metadata=chunk_meta,
                )
            )

        logger.info(f"[StructuredChunker] 切片完成: {file_name} -> 产出 {len(final_chunks)} 个切片")
        return final_chunks

    def _split_large_block(self, text: str) -> List[str]:
            """递归平滑截断单个超大文本块"""
            separators = ["\n\n", "\n", "。", "；", "！", "？", " ", ""]
            parts: List[str] = []
            start = 0
            n = len(text)
            while start < n:
                end = start + self.chunk_size
                if end >= n:
                    chunk = text[start:n].strip()
                    if chunk:
                        parts.append(chunk)
                    break

                sub_str = text[start:end]
                split_pos = -1
                for sep in separators[:-1]:
                    pos = sub_str.rfind(sep)
                    if pos != -1 and pos > (self.chunk_size // 3):
                        split_pos = pos + len(sep)
                        break
                if split_pos == -1:
                    split_pos = self.chunk_size

                chunk = text[start:start + split_pos].strip()
                if chunk:
                    parts.append(chunk)
                start += max(1, split_pos - self.chunk_overlap)

            return parts


# 兼容别名
StructuredChunk = StructuredChunker


