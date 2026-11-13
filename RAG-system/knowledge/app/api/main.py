import json
from pathlib import Path
from typing import Optional, Literal, Dict, List

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.answering import answer_generator
from app.ingestion.batch_executor import BatchExecutor, BatchExecutionResult, SingleFileResult
from pydantic import BaseModel, Field

from app.retrieval.hybrid_retriever import HybridRetriever
from loguru import logger

app = FastAPI(
    title="Enterprise knowledge base api",
    description="企业规章制度向量知识库受控批次摄取与管理接口",
    version="1.0.0",
)

# 配置cors
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化全局批处理调度器单例
executor = BatchExecutor()
# 初始化检索器与问答器单例
retriever = HybridRetriever()
qa_engine = answer_generator.AnswerGenerator(retriever)

class RetrieveRequest(BaseModel):
    query: str = Field(...,min_length=1,description="检索问题或关键词")
    top_k: int = Field(default=5, ge=1, le=20, description="返回切片数量 (1~20)")
    mode: Literal["hybrid", "dense", "sparse"] = Field(default="hybrid", description="检索模式")

class QARequest(BaseModel):
    question: str = Field(..., min_length=1, description="员工自然语言提问")
    top_k: int = Field(default=5, ge=1, le=15, description="送入上下文的候选证据数量")
    mode: Literal["hybrid", "dense", "sparse"] = Field(default="hybrid", description="检索模式")


class BatchInjestRequest(BaseModel):
    batch_size: int = Field(
        default=5,
        ge=1,
        le=50,
        description="单批次处理文件数量 (1~50)"
    )
    file_ext: Optional[str] = Field(
        default=None,
        description="按文件类型分组筛选 (如 pdf, docx, xlsx, image 等)"
    )
    file_ids: Optional[List[int | str]] = Field(
        default=None,
        description="指定入库的文件 ID 列表 (精准单选或多选)"
    )

FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="assets")


@app.get("/")
def serve_console():
    """直接访问 http://localhost:8000 返回编译后的 Vue 3 + Element-Plus-X 生产工作台"""
    dist_html = FRONTEND_DIST_DIR / "index.html"
    if dist_html.exists():
        return FileResponse(dist_html)
    html_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "index.html"
    return FileResponse(html_path)

@app.get("/api/v1/kb/health")
def health_check():
    """健康检查接口"""
    return {"status": "healthy"}

@app.get("/api/v1/kb/overview")
def get_overview():
    """获取全局指标看板统计"""
    return executor.get_overview_metrics()

@app.get("/api/v1/kb/files")
def list_files(
    status: Optional[str] = Query(default=None, description="状态筛选: ALL, PENDING, PROCESSING, COMPLETED, FAILED"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=100),
    file_ext: Optional[str] = Query(default=None, description="文件类型分组筛选 (如 pdf, docx, xlsx, image 等)")
):
    """分页获取文件列表与状态，附带各扩展名聚合统计分布"""
    return executor.get_files_paginated(status=status, page=page, page_size=page_size, file_ext=file_ext)


@app.post("/api/v1/kb/ingest/batch", response_model=BatchExecutionResult)
def trigger_batch_ingest(req: BatchInjestRequest):
    """
    核心受控批次导入入口：
    支持全局拉取、按文件类型分组拉取 (file_ext)、或按选定文件 ID 列表精准批量入库 (file_ids)
    """
    return executor.execute_batch(
        batch_size=req.batch_size,
        file_ext=req.file_ext,
        file_ids=req.file_ids,
    )

@app.post("/api/v1/kb/ingest/file/{file_id}", response_model=SingleFileResult)
def trigger_single_file_ingest(file_id: int):
    """
    单文件精准解析与向量化入库：
    清空该文件旧切片并立即重新提取文本、生成切片与写入向量
    """
    return executor.process_file_by_id(file_id=file_id)

@app.post("/api/v1/kb/reset-failed")
def reset_failed():
    """将所有状态为FAILED 的文件重置为 PENDING"""
    count = executor.reset_failed_files()
    return {"reset_count": count, "message": f"已重置 {count} 个失败文件"}

@app.get("/api/v1/kb/files/{file_id}/chunks")
def get_chunks(file_id: int):
    chunks = executor.get_file_chunks(file_id=file_id)
    return {
        "file_id": str(file_id),
        "chunk_count": len(chunks),
        "chunks": chunks
    }

@app.post("/api/v1/kb/retrieve")
def retrieve_chunks(req:RetrieveRequest):
    """独立检索调试接口：支持对比 hybrid / dense / sparse 三种模式的召回明细"""
    chunks = retriever.retrieve(
        query=req.query,
        top_k=req.top_k,
        mode=req.mode,
    )
    return {
        "query": req.query,
        "top_k": req.top_k,
        "mode": req.mode,
        "count": len(chunks),
        "items": chunks,
    }

@app.post("/api/v1/kb/qa", response_model=answer_generator.QAResponse)
def ask_knowledge_base(req: QARequest):
    """受控证据引用制度问答接口"""
    return qa_engine.answer(question=req.question, top_k=req.top_k, mode=req.mode)


@app.get("/api/v1/kb/audit-report")
def get_corpus_audit_report():
    """
    获取全量 215 份语料体检报告快照 (供前端运维看板可视化展示)
    """
    project_root = Path(__file__).resolve().parents[2]
    report_file = project_root / "data" / "corpus_audit_report.json"
    if not report_file.exists():
        return {
            "has_report": False,
            "message": "尚未生成体检报告，请在终端执行: python app/ingestion/corpus_auditor.py",
            "total": 0,
            "records": [],
            "summary": {}
        }
    
    try:
        with open(report_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        # 实时聚合汇总卡片数据
        total = len(records)
        healthy = sum(1 for r in records if r.get("status") == "HEALTHY")
        scan_pdf = sum(1 for r in records if r.get("status") == "SCAN_PDF")
        needs_ocr = sum(1 for r in records if r.get("needs_ocr"))
        corrupted = sum(1 for r in records if r.get("status") == "CORRUPTED")
        encrypted = sum(1 for r in records if r.get("status") == "ENCRYPTED")
        download_failed = sum(1 for r in records if r.get("status") == "DOWNLOAD_FAILED")
        duplicates = sum(1 for r in records if r.get("is_duplicate"))

        ext_stat: Dict[str, int] = {}
        for r in records:
            ext = r.get("file_ext", "other")
            ext_stat[ext] = ext_stat.get(ext, 0) + 1

        return {
            "has_report": True,
            "total": total,
            "records": records,
            "summary": {
                "healthy": healthy,
                "scan_pdf": scan_pdf,
                "needs_ocr": needs_ocr,
                "corrupted": corrupted,
                "encrypted": encrypted,
                "download_failed": download_failed,
                "duplicates": duplicates,
                "ext_stat": ext_stat,
            }
        }
    except Exception as e:
        logger.error(f"[AuditReportAPI] 读取体检报告异常: {e}")
        return {
            "has_report": False,
            "message": f"读取体检报告文件失败: {e}",
            "total": 0,
            "records": [],
            "summary": {}
        }


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    """SPA 路由兜底支持：使 /qa, /dataset, /retrieve, /ingest 等前端路由刷新时不报 404"""
    if full_path.startswith("api/") or full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Resource Not Found")
    dist_html = FRONTEND_DIST_DIR / "index.html"
    if dist_html.exists():
        return FileResponse(dist_html)
    html_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "index.html"
    return FileResponse(html_path)

