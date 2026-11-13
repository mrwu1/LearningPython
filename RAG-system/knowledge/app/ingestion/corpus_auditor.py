import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from app.db.connection import get_db_connection
from pypdf import PdfReader
from docx import Document
import openpyxl
from loguru import logger
from pydantic import BaseModel, Field

from dotenv import load_dotenv, find_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(find_dotenv())


class FileAuditRecord(BaseModel):
    """单文件全量体检详细记录（生产级契约）"""
    file_id: int
    file_name: str
    file_ext: str
    declared_size: Optional[int] = None
    actual_size: int = 0
    content_sha256: str = ""
    is_duplicate: bool = False
    duplicate_with_ids: List[int] = Field(default_factory=list)
    
    # 状态标记
    status: str = "PENDING"  # HEALTHY, SCAN_PDF, ENCRYPTED, CORRUPTED, OVERSIZED, DOWNLOAD_FAILED
    http_status: int = 0
    magic_valid: bool = False
    needs_ocr: bool = False
    
    # 深度结构度量
    total_pages_or_sheets: int = 0
    scan_pages_count: int = 0
    paragraph_or_row_count: int = 0
    table_count: int = 0
    
    error_msg: Optional[str] = None


class CorpusAuditor:
    """
    企业级全量语料体检器 (Production Corpus Auditor)：
    1. 覆盖 215 份未删除文件，执行严格的 HTTP 拉取与魔数检测
    2. 计算 content_sha256 并识别内容完全重复的冗余文件簇
    3. 多格式深度探针：PDF 扫描页探测、Word/Excel 结构与加密检测
    4. 内存大小保护 (上限 100MB) 与网络断点容错
    5. 体检结果持久化保存为 data/corpus_audit_report.json 供前端工作台直接读取
    """
    MAGIC_SIGNATURES = {
        ".pdf": b"%PDF-",
        ".docx": b"PK\x03\x04",
        ".xlsx": b"PK\x03\x04",
        ".pptx": b"PK\x03\x04",
        ".doc": b"\xd0\xcf\x11\xe0",
        ".xls": b"\xd0\xcf\x11\xe0",
        ".jpg": b"\xff\xd8\xff",
        ".jpeg": b"\xff\xd8\xff",
        ".png": b"\x89PNG\r\n\x1a\n",
    }
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB 保护上限

    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout_seconds = timeout_seconds
        self.client = httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds, connect=5.0),
            follow_redirects=True
        )
        self.report_dir = PROJECT_ROOT / "data"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _get_active_files(self) -> List[Dict[str, Any]]:
        """从数据库读取全部有效文件元数据（严格对齐真实 kb.kb_file 表结构）"""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, url, file_ext, file_type
                    FROM kb.kb_file
                    WHERE delete_flag = FALSE
                    ORDER BY id ASC;
                """)
                rows = cur.fetchall()
                return [
                    {
                        "file_id": r[0],
                        "name": r[1],
                        "url": r[2],
                        "file_ext": r[3],
                        "file_type": r[4],
                    }
                    for r in rows
                ]

    def audit_single_file(self, file_meta: Dict[str, Any]) -> FileAuditRecord:
        """单文件多格式深度体检探针"""
        fid = file_meta["file_id"]
        fname = file_meta["name"]
        url = file_meta["url"]
        
        # 优先使用数据库中已有的 file_ext，并规范为带点小写
        db_ext = (file_meta.get("file_ext") or "").strip().lower()
        if db_ext:
            ext = f".{db_ext}" if not db_ext.startswith(".") else db_ext
        else:
            ext = Path(fname).suffix.lower()

        record = FileAuditRecord(
            file_id=fid,
            file_name=fname,
            file_ext=ext,
            declared_size=None,
        )

        # 独立图片直接标记需要 OCR
        if ext in [".jpg", ".jpeg", ".png"]:
            record.needs_ocr = True

        try:
            resp = self.client.get(url)
            record.http_status = resp.status_code
            if resp.status_code != 200:
                record.status = "DOWNLOAD_FAILED"
                record.error_msg = f"HTTP 状态码: {resp.status_code}"
                return record

            content_bytes = resp.content
            record.actual_size = len(content_bytes)

            # 内存溢出防御
            if record.actual_size > self.MAX_FILE_SIZE:
                record.status = "OVERSIZED"
                record.error_msg = f"文件超过 100MB 限制: {record.actual_size} bytes"
                return record

            # 计算内容 SHA-256
            record.content_sha256 = hashlib.sha256(content_bytes).hexdigest()

            # 魔数校验
            expected_magic = self.MAGIC_SIGNATURES.get(ext)
            if expected_magic:
                if content_bytes.startswith(expected_magic):
                    record.magic_valid = True
                else:
                    record.magic_valid = False
                    record.status = "CORRUPTED"
                    record.error_msg = f"文件头魔数与扩展名 {ext} 不符"
                    return record
            else:
                record.magic_valid = True

            # 格式深度结构探针
            if ext == ".pdf":
                self._inspect_pdf(content_bytes, record)
            elif ext == ".docx":
                self._inspect_docx(content_bytes, record)
            elif ext == ".xlsx":
                self._inspect_xlsx(content_bytes, record)

            if record.status == "PENDING":
                record.status = "HEALTHY"

        except Exception as e:
            record.status = "DOWNLOAD_FAILED"
            record.error_msg = str(e)

        return record

    def _inspect_pdf(self, content_bytes: bytes, record: FileAuditRecord):
        """PDF 深度探针：页数、字符密度与扫描件检测（支持 AES 权限只读密码自动解密）"""
        try:
            reader = PdfReader(BytesIO(content_bytes))
            if reader.is_encrypted:
                decrypt_success = False
                try:
                    # 尝试空密码解密（绝大多数企业制度/官方表单属于限制打印/修改，阅读密码为空）
                    # reader.decrypt("") 返回 1 (User password) 或 2 (Owner password)
                    res = reader.decrypt("")
                    if res in (1, 2, True):
                        decrypt_success = True
                except Exception:
                    pass

                if not decrypt_success:
                    record.status = "ENCRYPTED"
                    record.error_msg = "PDF 被强口令加密，无法自动读取"
                    return

            record.total_pages_or_sheets = len(reader.pages)
            scan_pages = 0

            for page in reader.pages:
                text = (page.extract_text() or "").strip()
                # 页面正文字数少于 30 个字且包含图片资源，判定为扫描/纯图片页
                if len(text) < 30 and len(page.images) > 0:
                    scan_pages += 1

            record.scan_pages_count = scan_pages
            if scan_pages > 0:
                record.needs_ocr = True
                # 若半数以上是扫描页，判定为扫描 PDF
                if scan_pages >= (record.total_pages_or_sheets / 2):
                    record.status = "SCAN_PDF"

        except Exception as e:
            record.status = "CORRUPTED"
            record.error_msg = f"PDF 解析损坏: {e}"

    def _inspect_docx(self, content_bytes: bytes, record: FileAuditRecord):
        """DOCX 深度探针：段落数、表格数与损坏检查"""
        try:
            doc = Document(BytesIO(content_bytes))
            record.paragraph_or_row_count = len(doc.paragraphs)
            record.table_count = len(doc.tables)
        except Exception as e:
            record.status = "CORRUPTED"
            record.error_msg = f"DOCX 损坏或加密: {e}"

    def _inspect_xlsx(self, content_bytes: bytes, record: FileAuditRecord):
        """XLSX 深度探针：工作表数量与行数探测"""
        try:
            wb = openpyxl.load_workbook(BytesIO(content_bytes), read_only=True, data_only=True)
            record.total_pages_or_sheets = len(wb.sheetnames)
            total_rows = 0
            for sname in wb.sheetnames:
                ws = wb[sname]
                total_rows += (ws.max_row or 0)
            record.paragraph_or_row_count = total_rows
            wb.close()
        except Exception as e:
            record.status = "CORRUPTED"
            record.error_msg = f"XLSX 损坏或加密: {e}"

    def run_full_audit(self) -> List[FileAuditRecord]:
        """执行全量体检、去重分析与落盘持久化"""
        files = self._get_active_files()
        total_files = len(files)
        logger.info(f"🚀 开始全量 215 份有效文件深度体检 (delete_flag = FALSE)...")

        results: List[FileAuditRecord] = []
        sha_map: Dict[str, List[int]] = defaultdict(list)
        start_time = time.perf_counter()

        # 1. 逐文件深度探测
        for idx, f in enumerate(files, start=1):
            rec = self.audit_single_file(f)
            results.append(rec)
            if rec.content_sha256:
                sha_map[rec.content_sha256].append(rec.file_id)

            status_symbol = "✅" if rec.status == "HEALTHY" else "⚠️"
            if rec.status in ["DOWNLOAD_FAILED", "CORRUPTED", "ENCRYPTED"]:
                status_symbol = "❌"
            ocr_flag = " [需OCR]" if rec.needs_ocr else ""
            print(f"[{idx:03d}/{total_files:03d}] {status_symbol} [{rec.file_ext:<5}] {rec.file_name[:38]:<38} | 状态: {rec.status:<8}{ocr_flag}")

        # 2. SHA-256 内容完全重复分析（聚类）
        duplicate_clusters = 0
        for rec in results:
            if rec.content_sha256 and len(sha_map[rec.content_sha256]) > 1:
                rec.is_duplicate = True
                rec.duplicate_with_ids = [fid for fid in sha_map[rec.content_sha256] if fid != rec.file_id]

        for sha, fids in sha_map.items():
            if len(fids) > 1:
                duplicate_clusters += 1

        elapsed = time.perf_counter() - start_time
        logger.info(f"🏁 全量体检完成！总耗时: {elapsed:.2f}s | 发现 {duplicate_clusters} 组完全重复文件")

        # 3. 持久化落盘到 data/corpus_audit_report.json
        report_file = self.report_dir / "corpus_audit_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in results], f, ensure_ascii=False, indent=2)
        logger.info(f"💾 完整体检记录已持久化落盘至: {report_file}")

        self._print_summary(results, duplicate_clusters)
        return results

    @staticmethod
    def _print_summary(results: List[FileAuditRecord], duplicate_clusters: int):
        """输出高维度分析大表"""
        total = len(results)
        healthy = sum(1 for r in results if r.status == "HEALTHY")
        scan_pdf = sum(1 for r in results if r.status == "SCAN_PDF")
        needs_ocr = sum(1 for r in results if r.needs_ocr)
        corrupted = sum(1 for r in results if r.status == "CORRUPTED")
        encrypted = sum(1 for r in results if r.status == "ENCRYPTED")
        download_failed = sum(1 for r in results if r.status == "DOWNLOAD_FAILED")
        duplicates = sum(1 for r in results if r.is_duplicate)

        ext_stat: Dict[str, int] = {}
        for r in results:
            ext_stat[r.file_ext] = ext_stat.get(r.file_ext, 0) + 1

        print("\n" + "=" * 90)
        print("📊 全量 215 份企业制度语料生产级体检大表 (Corpus Production Audit Report)")
        print("=" * 90)
        print(f"有效文件总数 (delete_flag=FALSE)    : {total}")
        print(f"原生健康文档 (HEALTHY)             : {healthy} ({healthy/total*100:.1f}%)")
        print(f"以扫描图片为主的 PDF (SCAN_PDF)     : {scan_pdf} ({scan_pdf/total*100:.1f}%)")
        print(f"全库需接入 OCR 文件数 (含图片+扫描PDF): {needs_ocr} ({needs_ocr/total*100:.1f}%)")
        print(f"内容完全重复的冗余文件数 (DUPLICATE) : {duplicates} 份 (分布在 {duplicate_clusters} 个文件簇中)")
        print(f"损坏文件 (CORRUPTED)                : {corrupted}")
        print(f"加密文件 (ENCRYPTED)                : {encrypted}")
        print(f"下载失败 (DOWNLOAD_FAILED)          : {download_failed}")
        print("-" * 90)
        print("📁 语料格式全景分布:")
        for ext, count in sorted(ext_stat.items(), key=lambda x: x[1], reverse=True):
            print(f"   {ext:<8} : {count:3d} 份")
        print("=" * 90 + "\n")


if __name__ == "__main__":
    auditor = CorpusAuditor()
    auditor.run_full_audit()
