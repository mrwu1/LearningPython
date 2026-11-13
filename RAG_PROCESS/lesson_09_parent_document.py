"""lesson_09_parent_document.py

    阶段三 · 3.2 父子文档检索 (Parent-Document / Small-to-Big Retrieval)
    核心目标：
    1. 解决 RAG 经典切片悖论：切太碎缺上下文，切太大向量相似度被稀释；
    2. 子切片 (Child Chunk) 注入向量库，负责高精语义相似度召回；
    3. 父文档 (Parent Doc) 保存在 DocStore 中，命中子切片后通过 parent_id 自动“回表”召回整章完整上下文；
    4. 演示自动去重：当同一章节的多个子切片被召回时，只向 LLM 注入一份完整的父文档。
"""
from typing import Dict, List, Tuple

from lesson_03_chroma_store import MiniChromaCollection

"""向量数据库底层的四元组存储结构"""
# doc_id: str
# document: str
# embedding: list[float]
# metadata: dict[str, Any] = field(default_factory=dict)  ✅： parent_id 在这里
class ParentDocumentRetriever:
    """父子文档检索器（Small-to-Big Retriever）"""
    def __init__(self,vector_kb:MiniChromaCollection):
        self.vector_kb = vector_kb # 向量数据库
        self.docstore:Dict[str,str] = {} # db数据库 key - value

    def add_documents(
        self,
        parent_docs:List[Tuple[str,str]], # [(parent_id, full_parent_text)]
        child_splitter_fn, # 切分子切片的函数
        embedding_fn # 计算子切片向量的函数
    ):
        """注册父文档，自动切分为子切片并存入向量库"""
        child_ids=[]
        child_texts=[]
        child_embeddings=[]
        child_metadatas = []
        for parent_id,parent_text in parent_docs:# [("doc_1","this is a document!")
            # 1. 存入母表 DocStore
            self.docstore[parent_id] = parent_text
            # 2. 将大父文档拆解为数个精细的子切片
            children = child_splitter_fn(parent_text)
            for idx, child_text in enumerate(children):
                c_id = f"{parent_id}_c{idx}"
                child_ids.append(c_id)
                child_texts.append(child_text)
                child_embeddings.append(embedding_fn(child_text))
                # 🌟 关键设计：子切片元数据必须牢牢绑定母体 parent_id！
                child_metadatas.append(
                    {"parent_id": parent_id, "child_index": idx}
                )
        # 3. 将小切片 upsert 到向量库
        self.vector_kb.upsert(
            ids=child_ids,
            documents=child_texts,
            embeddings=child_embeddings,
            metadatas=child_metadatas,
        )
        print(
            f"📦 [父子索引构建完成] 注册父文档 {len(parent_docs)} 篇，生成子切片 {len(child_ids)} 个。"
        )

    def retrieve(
            self,
            query_vector: List[float],
            k_children: int = 3
    ) -> List[Tuple[str, str]]:
            """检索流程：检索子向量 -> 提取 parent_id -> 自动回表并去重 -> 返回完整父文档"""
            # 1. 在子切片空间进行近邻检索
            child_hits = self.vector_kb.similarity_search_with_score(
                query_vector, k=k_children
            )

            print(f"   🔍 命中 {len(child_hits)} 个子切片:")
            print(f"child_hits:{child_hits}")
            for rec, sim, _ in child_hits:
                p_id = rec.metadata.get("parent_id")
                print(
                    f"-rec是什么：{rec} [子切片 {rec.doc_id}] 相似度={sim:.4f} -> 归属母文档: {p_id}"
                )
                print(f"子切片文本: {rec.document[:45]}...")

            # 2. 收集 parent_id 并去重 (保持召回顺序)
            seen_parent_ids = set()
            ordered_parent_ids = []
            for rec, _, _ in child_hits:
                p_id = rec.metadata.get("parent_id")
                if p_id and p_id not in seen_parent_ids:
                    seen_parent_ids.add(p_id)
                    ordered_parent_ids.append(p_id)

            # 3. 回表从 DocStore 调出完整父文档 - 推导式
            retrieved_parents = [
                (pid, self.docstore[pid]) for pid in ordered_parent_ids
            ]
            # retrieved_parents = [
            #     ("p3", {"content": "文档三"}),
            #     ("p1", {"content": "文档一"}),
            #     ("p2", {"content": "文档二"}),
            # ]
            return retrieved_parents
        # parent_docs = [
        #     ("DOC-CH-2-TRAVEL", parent_chapter_2),
        #     ("DOC-CH-3-TEAM", parent_chapter_3),
        # ],
        # child_splitter_fn = mock_child_splitter,
        # embedding_fn = mock_child_embedding,


if __name__ == "__main__":
    # 构造一篇极具代表性的企业长制度：第二章 差旅合规管理办法（超长父文档）
    parent_chapter_2 = (
        "【第二章 差旅合规与特殊报销管理办法】\n"
        "第一节 职级标准：集团副总裁级别每日住宿限额800元；总监级别每日限额500元；普通员工每日限额350元。\n"
        "第二节 超标前置审批：因业务紧急或当地旺季导致房费超标20%以内的，须提前在OA提交《特殊费用预先申请单》，"
        "由二级部门一把手与财务总监双重电子会签审批通过后，方可予以实报实销。\n"
        "第三节 违规惩戒与追偿：凡未经事前特批擅自超标入住的，超出部分一律由员工个人全额自行承担；"
        "连续两次严重超标者，财务合规部门将通报批评并暂停其个人差旅报销资格半年。"
    )

    parent_chapter_3 = (
        "【第三章 员工福利与团队建设经费管理办法】\n"
        "第一节 团建预算：各技术与业务部门每季度享有每人300元的团队建设专项经费，不得用于个人充值或跨季度累计。\n"
        "第二节 报销票据：团建经费仅接受餐饮发票、正规拓展机构增值税发票，且必须附全员合影打卡记录作为附件。"
    )


    # 简易子切片切分器：按句号/分号切开，模拟 60~100 字细粒度切片
    def mock_child_splitter(text: str) -> List[str]:
        # 简单过滤空行并切成若干子条款
        raw_chunks = [c.strip() for c in text.replace("\n", "").split("。")]
        return [c + "。" for c in raw_chunks if len(c) > 10]

    # 简易特征模拟：为演示直观，用 4 维特征向量


    # [差旅标准, 超标审批, 团建福利, 处罚条款]
    def mock_child_embedding(child_text: str) -> List[float]:
        if "超标前置审批" in child_text:
            return [0.4, 0.95, 0.0, 0.1]
        elif "职级标准" in child_text:
            return [0.95, 0.3, 0.0, 0.1]
        elif "违规惩戒" in child_text:
            return [0.2, 0.2, 0.0, 0.95]
        elif "团建" in child_text:
            return [0.0, 0.0, 0.95, 0.0]
        return [0.1, 0.1, 0.1, 0.1]


    # 1. 初始化底座
    child_vector_kb = MiniChromaCollection(name="child_chunks_kb")
    parent_retriever = ParentDocumentRetriever(vector_kb=child_vector_kb)

    # 2. 注入两篇大父文档
    parent_retriever.add_documents(
        parent_docs=[
            ("DOC-CH-2-TRAVEL", parent_chapter_2),
            ("DOC-CH-3-TEAM", parent_chapter_3),
        ],
        child_splitter_fn=mock_child_splitter,
        embedding_fn=mock_child_embedding,
    )

    print("\n" + "=" * 80)
    print("🚀 测试：用户询问细节条款（如超标怎么特批报销？）")
    # 提问向量强烈倾向 [超标审批] 特征
    query_vector = [0.35, 0.92, 0.01, 0.15]

    results = parent_retriever.retrieve(query_vector=query_vector, k_children=2)

    print("\n🏆 [Small-to-Big 最终注入 LLM 的父文档上下文]:")
    for pid, full_content in results:
        print(f"\n📄 母文档 ID: [{pid}]")
        print(f"📖 完整上下文内容:\n{full_content}")