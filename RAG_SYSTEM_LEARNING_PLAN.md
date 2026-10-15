# 📚 RAG 检索增强生成与企业级知识库实战指南

> **授课模式**：导师制一对一课件授课 ｜ 随堂手撕原生代码 ｜ 逐行 Code Review ｜ 拒绝死记文档与黑盒框架  
> **适用对象**：具备 Java 工程师背景，正全面转型现代 Python AI Agent 与企业知识库开发的开发者。  
> **核心原则**：从最底层的向量数学与切片算法，到向量数据库、混合检索及 Agentic RAG 融合！

---

## 一、 心智模型对齐（Java ES vs 现代 RAG 向量检索）

| 维度 | Java 传统全文检索（ES/Lucene） | 现代 RAG 向量检索（Vector Search） | 核心心智差异 / 工业落地要点 |
| :--- | :--- | :--- | :--- |
| **底层表示** | 文本倒排索引（Inverted Index） | 高维致密浮点数向量（Dense Embeddings） | 传统检索只认字面出现频次；向量检索理解上下文语义（同义词、近义词）。 |
| **匹配计算** | TF-IDF / BM25 词频统计匹配 | 余弦相似度（Cosine Similarity）/ 点积（Dot Product） | 在 1536 维语义空间中计算两段话的夹角余弦，夹角越小越相似。 |
| **输入约束** | 无需严格切片，支持整篇文章全文索引 | 必须精细切片（Chunking with Overlap） | Embedding 模型与 LLM 上下文均有长度上限，且切片越小检索精度越高。 |
| **专有名词表现** | 极强（精准命中型号、订单号、股票代码） | 稍弱（容易出现近义泛化导致命中偏差） | 工业界必用**混合检索（Hybrid Search: 向量 + BM25）**进行长短互补。 |
| **与 Agent 融合** | 仅仅是一个检索 API | 智能体的外部长期记忆与知识挂载（Agentic RAG） | Agent 可自主决策何时调起检索工具，边查规章制度边执行业务调用。 |

---

## 二、 学习进度打卡表

| 课时 | 核心知识点 | 状态 | 交付物/代码文件 | 完成时间 |
| :---: | :--- | :---: | :--- | :---: |
| **第 1 课** | 初识 Embedding 向量与余弦相似度数学直觉 | ⏳ 进行中 | `src/rag_study/lesson_01_cosine_similarity.py` | - |
| **第 2 课** | 文档切片黄金法则（Chunking & Overlap） | ⏳ 待开始 | `src/rag_study/lesson_02_chunking_strategy.py` | - |
| **第 3 课** | 向量数据库实战：存储、Metadata过滤与Top-K检索 | ⏳ 待开始 | `src/rag_study/lesson_03_vector_database.py` | - |
| **第 4 课** | 原生 Naive RAG 闭环：上下文注入与防幻觉Prompt | ⏳ 待开始 | `src/rag_study/lesson_04_naive_rag_pipeline.py` | - |
| **第 5 课** | 进阶：混合检索（Hybrid Search: 向量+BM25）与重排序 | ⏳ 待开始 | `src/rag_study/lesson_05_hybrid_search.py` | - |
| **第 6 课** | 毕业实战：Agentic RAG —— 将知识库封装为智能体工具 | ⏳ 待开始 | `src/rag_study/lesson_06_agentic_rag.py` | - |
