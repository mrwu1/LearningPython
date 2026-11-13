import io
import re
from typing import List, Dict, Any, Optional
import httpx
import jieba
from loguru import logger
from pydantic import BaseModel

from app.parsers.structured_chunker import StructuredChunker, DocumentChunk
from app.parsers.word_parser import WordParser
from app.parsers.excel_parser import ExcelParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.presentation_parser import PresentationParser
from app.parsers.image_parser import ImageParser
from app.parsers.ocr_service import ZhipuGLMOCRService


# 1. 定义解析结果契约 (DocumentChunk 直接复用 structured_chunker 契约，避免类身份不一致)
class ParseResult(BaseModel):
    file_id: int | str
    file_name: str
    chunks: List[DocumentChunk]
    raw_char_count: int


# 2. 核心异构文档多模态解析调度中枢 (门面模式 Facade)
class DocumentParser:
    """
    统一文档解析调度中枢：
    通过组合 WordParser, ExcelParser, PdfParser, PresentationParser, ImageParser,
    实现全格式 (PDF / Word / Excel / PPTX / 图片 / 扫描件) 的自动分流与切片。
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        timeout: float = 30.0,
        ocr_service: Optional[ZhipuGLMOCRService] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.timeout = timeout

        # OCR 智能识别服务
        self.ocr_service = ocr_service or ZhipuGLMOCRService()

        # 子格式解析器单例注入
        self.word_parser = WordParser()
        self.excel_parser = ExcelParser()
        self.pdf_parser = PdfParser(ocr_service=self.ocr_service)
        self.presentation_parser = PresentationParser()
        self.image_parser = ImageParser(ocr_service=self.ocr_service)

        # 👈 新增：结构化切片引擎
        self.structured_chunker = StructuredChunker(
            target_chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        # 预热 jieba 分词引擎
        jieba.initialize()

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """安全清洗：防御 PostgreSQL \\x00 致命字符，规整多余换行与制表符"""
        if not text:
            return ""
        # 必须剔除空字节，否则 PG TEXT 字段抛出 DataError
        text = text.replace("\x00", "")
        # 归一化换行符
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 将连续三个以上的换行压缩为 2 个
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_text_recursively(self, text: str) -> List[str]:
        """递归字符切片器：优先在段落和句号处切分，保留语义完整性"""
        if len(text) <= self.chunk_size:
            return [text] if text else []

        separators = ["\n\n", "\n", "。", "；", "！", "？", " ", ""]
        final_chunks: List[str] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size
            if end >= text_len:
                chunk = text[start:text_len].strip()
                if chunk:
                    final_chunks.append(chunk)
                break

            # 在有效窗口内寻找最近的自然分隔符
            sub_str = text[start:end]
            split_pos = -1
            for sep in separators[:-1]:
                pos = sub_str.rfind(sep)
                if pos != -1 and pos > (self.chunk_size // 3):  # 至少保留前 1/3 长度
                    split_pos = pos + len(sep)
                    break

            if split_pos == -1:
                split_pos = self.chunk_size

            chunk = text[start : start + split_pos].strip()
            if chunk:
                final_chunks.append(chunk)

            # 滑动起始点 (减去 overlap)
            start += max(1, split_pos - self.chunk_overlap)

        return final_chunks

    def parse_bytes(
        self,
        content_bytes: bytes,
        file_id: int | str,
        file_name: str,
        file_ext: str,
        url: Optional[str] = None,
    ) -> ParseResult:
        """从二进制字节流直接分流解析并构建标准化切片"""
        ext = file_ext.lower().strip().lstrip(".")
        logger.info(f"[Parser] 开始解析文档: {file_name} (ID: {file_id}, 格式: {ext}, 大小: {len(content_bytes)} 字节)")

        raw_blocks: List[str] = []

        # 格式分流调度
        if ext == "pdf":
            raw_blocks = self.pdf_parser.parse_pdf(
                content_bytes=content_bytes, url=url, file_name=file_name
            )
        elif ext == "docx":
            raw_blocks = self.word_parser.parse_docx(content_bytes)
        elif ext == "doc":
            raw_blocks = self.word_parser.parse_doc(content_bytes)
        elif ext == "xlsx":
            raw_blocks = self.excel_parser.parse_xlsx(content_bytes)
        elif ext == "xls":
            raw_blocks = self.excel_parser.parse_xls(content_bytes)
        elif ext in ["pptx", "ppt"]:
            raw_blocks = self.presentation_parser.parse_pptx(content_bytes)
        elif ext in ["png", "jpg", "jpeg", "bmp", "webp"]:
            raw_blocks = self.image_parser.parse_image(
                content_bytes=content_bytes, url=url, file_name=file_name
            )
        elif ext in ["md", "markdown", "txt"]:
            raw_blocks = [content_bytes.decode("utf-8", errors="ignore")]
        else:
            logger.warning(f"暂未受支持的文件格式，跳过提取: {ext}")
            return ParseResult(file_id=file_id, file_name=file_name, chunks=[], raw_char_count=0)

        # 聚合清洗后的完整内容
        sanitized_blocks = [self._sanitize_text(b) for b in raw_blocks if self._sanitize_text(b)]
        full_text = "\n\n".join(sanitized_blocks)

        if not full_text.strip():
            logger.warning(f"[Parser] 文档内容提取为空: {file_name}")
            return ParseResult(file_id=file_id, file_name=file_name, chunks=[], raw_char_count=0)

        # 👈 核心替换：先按行打碎为语义积木，再装箱为结构化切片
        raw_lines = [line.strip() for b in sanitized_blocks for line in b.split("\n") if line.strip()]
        blocks = self.structured_chunker.segment_into_blocks(raw_lines)
        final_chunks = self.structured_chunker.build_chunks(
                blocks=blocks,
                file_id=file_id,
                file_name=file_name,
                file_ext=ext,
          )
        logger.info(
            f"[Parser] 解析完成: {file_name} -> 原始字符: {len(full_text)}, 产出切片: {len(final_chunks)}"
        )
        return ParseResult(
            file_id=file_id,
            file_name=file_name,
            chunks=final_chunks,
            raw_char_count=len(full_text),
        )

    def parse_from_cos(
        self,
        url: str,
        file_id: int | str,
        file_name: str,
        file_ext: str,
    ) -> ParseResult:
        """从 COS/HTTP 下载二进制流后进行多模态解析"""
        ext = file_ext.lower().strip().lstrip(".")
        logger.info(f"[Parser] 开始从 COS 下载并解析: {file_name} (ID: {file_id}, 格式: {ext})")

        with httpx.Client(verify=False, follow_redirects=True, timeout=self.timeout) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"COS 下载失败，HTTP 状态码: {resp.status_code}")
            content_bytes = resp.content

        return self.parse_bytes(
            content_bytes=content_bytes,
            file_id=file_id,
            file_name=file_name,
            file_ext=ext,
            url=url,
        )
