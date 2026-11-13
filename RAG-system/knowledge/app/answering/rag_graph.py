import os
from urllib.parse import quote_plus

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel,Field
from typing import TypedDict, List, Dict, Optional, Literal, Any
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, START, END
from loguru import logger
from app.answering.answer_generator import AnswerGenerator, QAResponse
from psycopg_pool import ConnectionPool

from app.retrieval.hybrid_retriever import RetrievedChunk

load_dotenv(find_dotenv())

class GraphQAResponse(QAResponse):
    """多轮状态机问答响应契约（在单轮 QAResponse 基础上扩展会话与自省轨迹字段）"""
    session_id: str = Field(description="多轮会话隔离标识 thread_id")
    rewritten_query:str = Field(description="经指代消解或重检索改写后的独立查询句")
    retry_count:int = Field(default=0,description="CRAG触发重检索的次数（0或1）")
    grade_status:str = Field(default="RELEVANT",description="证据评估状态：RELEVANT 或 IRRELEVANT")

# 2. 定义“公共黑板” (State) —— 全部使用原生类型以便 PostgresSaver 序列化落盘
class RAGGraphState(TypedDict, total=False):
        chat_history: List[Dict[str, str]]       # 跨轮次持久化在 PostgreSQL 中的对话历史
        original_question: str                   # 本轮员工原话
        rewritten_query: str                     # 1号工位产出的独立检索句
        mode: Literal["hybrid", "dense", "sparse"]
        top_k: int
        retrieved_chunks: List[Dict]             # 2号工位产出的切片字典列表
        grade_status: str                        # 3号工位产出的验货结果: RELEVANT / IRRELEVANT
        retry_count: int                         # 重试计数器
        qa_response: Dict                        # 4号工位产出的问答结果字典

class RAGWorkflow:
    """
    基于langGraph的 企业多规章制度多轮自省问答工作流：
    1.
    """
    def __init__(self,qa_engine: Optional[AnswerGenerator] = None):
        self.qa_engine = qa_engine or AnswerGenerator()
        self.retriever = self.qa_engine.retriever
        self.client = self.qa_engine.client
        self.model = self.qa_engine.model

        # 初始化checkpointer
        self.pool = self._init_pg_pool()
        self.checkpointer = PostgresSaver(self.pool)
        # 自动创建表
        self.checkpointer.setup()
        logger.info("✅ [PostgresSaver] 会话状态持久化表已就绪")

        # 创建graph
        self.graph = self._build_graph()

    @staticmethod
    def _init_pg_pool():
        """构建连接池"""
        user = os.getenv("PG_USER", "postgres")
        password = quote_plus(os.getenv("PG_PASSWORD", ""))
        host = os.getenv("PG_HOST", "127.0.0.1")
        port = os.getenv("PG_PORT", "5432")
        dbname = os.getenv("PG_DB", "knowledge")
        db_uri = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        # 关键：autocommit=True 确保 checkpointer.setup() 中的 CREATE INDEX CONCURRENTLY 正常执行
        return ConnectionPool(
            conninfo=db_uri,
            min_size=1,
            max_size=20,
            kwargs={"autocommit":True}
        )

    # 1 号工位：结合历史对话，把带代词的追问改写为独立问题
    # history = [
    #     {"role": "user", "content": "帮我写一段Python代码..."},
    #     # ... 中间省略 6 条 ...
    #     {"role": "user", "content": "那如果要连接PostgreSQL，代码怎么改？"},  # 倒数第2条
    #     {"role": "assistant", "content": "你可以使用 psycopg2 库，具体步骤如下..."}  # 倒数第1条
    # ]
    def _node_rewrite(self,state: RAGGraphState)->RAGGraphState:
        """"""
        original_q = state["original_question"]
        history = state.get("chat_history") or []
        retry_count = state.get("retry_count", 0)

        #首轮提问且非重试：放行，不调用模型
        if not history and retry_count==0:
            return {"rewritten_query":original_q}
        history_str = " ".join([f"m:{m['role']}:{m['content'][:120]}" for m in history[-6:]])
        prompt = (
            f"请结合【对话历史】，将【当前提问】改写为一个主语明确、语义完整的独立检索句（消解‘它’、‘那’等代词，去除 无意义口语词）。\n"                                                                                      
            f"只输出改写后的句子本身，不要任何解释。\n\n"
            f"【对话历史】：\n{history_str or '无'}\n\n"
            f"【当前提问】：\n{original_q}\n\n"
            f"【独立检索句】："
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        rewritten = (resp.choices[0].message.content or original_q).strip()
        logger.info(f"[1.Rewrite] (retry={retry_count}) '{original_q}' -> '{rewritten}'")
        return {
            "rewritten_query": rewritten,
        }

    # 2 号工位：拿着改写后的独立问题去查数据库
    def _node_retrieve(self,state: RAGGraphState)->RAGGraphState:
        query = state["rewritten_query"]
        top_k = state["top_k"]
        mode = state.get("mode", "hybrid")
        chunks:List[RetrievedChunk] = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            mode=mode,
        )
        return {
            "retrieved_chunks": [c.model_dump() for c in chunks],
        }
    # 3 号工位：验货员（检查查出来的切片跟问题相不相关）
    def _node_grade(self,state: RAGGraphState)->RAGGraphState:
        chunks = state["retrieved_chunks"] or []
        retry_count = state.get("retry_count", 0)
        if not chunks:
            return {"grade_status": "IRRELEVANT", "retry_count": retry_count + 1}
        # 看第 1 名切片的向量相似度是否 >= 0.58，或者向量+全文双路同时命中
        top1 = chunks[0]
        dense_score = top1.get("dense_score")
        rank_d = top1.get("rank_d")
        rank_s = top1.get("rank_s")
        is_good = (dense_score is not None and dense_score >= 0.58) or (
                rank_d is not None and rank_s is not None
        )
        if is_good:
            logger.info(f"[3.Grade] 证据合格 (dense={dense_score}, rank_d={rank_d}, rank_s={rank_s})")
            return {"grade_status": "RELEVANT"} #❌

        logger.warning(f"[3.Grade] 证据相关性不足 (dense={dense_score}) -> 标记 IRRELEVANT")
        return {"grade_status": "IRRELEVANT", "retry_count": retry_count + 1} #✅

    # 红绿灯路由函数：决定去 4 号工位还是打回 1 号工位重试
    @staticmethod
    def _router_after_grade(state: RAGGraphState) -> str:
        if state.get("grade_status") == "RELEVANT":
            return "generate"
        if state.get("retry_count", 0) <= 1:
            logger.info("🔄 [Router] 触发 CRAG 重检索回路 (上限 1 次)...")
            return "rewrite"
        return "generate"

    def _node_generate(self,state: RAGGraphState)->RAGGraphState:
        rewritten_q = state["rewritten_query"]
        if state.get("grade_status") == "IRRELEVANT":
            qa_res = QAResponse(
                question=rewritten_q,
                mode=state.get("mode", "hybrid"),
                answer="未在当前企业知识库中检索到与该问题相关的制度依据。",
                has_evidence=False,
                citations=[],
                retrieved_candidates=[],
                model=self.model,
            )
        else:
            # 直接调用 AnswerGenerator（因 2 号工位已写入 Redis L2 缓存，此处检索耗时为 0ms）
            qa_res = self.qa_engine.answer(
                question=rewritten_q,
                top_k=state.get("top_k", 5),
                mode=state.get("mode", "hybrid"),
            )

        # 将本轮对话追加到历史记录，PostgresSaver 会自动将其落盘到 checkpoints 表
        history = list(state.get("chat_history") or [])
        history.append({"role":"user","content":state['original_question']})
        history.append({"role":"assistant","content":qa_res.answer})

        return{
            "qa_response": qa_res.model_dump(),
            "chat_history": history[-10:] # 保留最近 5 轮（10 条消息）
        }

    def _build_graph(self):
        builder = StateGraph(RAGGraphState)
        builder.add_node("rewrite", self._node_rewrite)
        builder.add_node("retrieve", self._node_retrieve)
        builder.add_node("grade", self._node_grade)
        builder.add_node("generate", self._node_generate)

        builder.add_edge(START,"rewrite")
        builder.add_edge("rewrite","retrieve")
        builder.add_edge("retrieve","grade")
        builder.add_conditional_edges(
            "grade",
            self._router_after_grade,
            {
                "generate":"generate",
                "rewrite":"rewrite",
            }
        )
        builder.add_edge("generate",END)
        return builder.compile(checkpointer= self.checkpointer)

    def ask(
                self,
                question: str,
                session_id: str = "default-session",
                top_k: int = 5,
                mode: Literal["hybrid", "dense", "sparse"] = "hybrid",
        ) -> GraphQAResponse:
            config = {"configurable": {"thread_id": session_id}}
            final_state = self.graph.invoke(
                {
                    "original_question": question,
                    "rewritten_query": question,
                    "mode": mode,
                    "top_k": top_k,
                    "retry_count": 0,
                },
                config=config,
            )
            qa_dict: Dict = final_state["qa_response"]
            return GraphQAResponse(
                **qa_dict,
                session_id=session_id,
                rewritten_query=final_state["rewritten_query"],
                retry_count=final_state.get("retry_count", 0),
                grade_status=final_state.get("grade_status", "RELEVANT"),
            )