# 📚 企业级 RAG 架构师体系化实战学习计划 (RAG from Scratch to Production)

> **核心参考标杆**：
> 1. **官方权威基石**：[langchain-ai/rag-from-scratch](https://github.com/langchain-ai/rag-from-scratch)（LangChain 官方核心工程师 Lance Martin 全套精讲体系）
> 2. **工业进阶字典**：[NirDiamant/RAG_Techniques](https://github.com/NirDiamant/RAG_Techniques)（全网 1.2 万+ Stars 工业高阶检索模式代码宝库）
> 3. **终极业务载体**：企业差旅报销与合规审计系统（对标硅谷 Ramp/Brex 自主财务风控中台）

---

## 目录
- [一、 核心学习原则与能力模型](#一-核心学习原则与能力模型)
- [二、 五大演进阶段详细规划](#二-五大演进阶段详细规划)
  - [阶段一：RAG 基石筑基与最小闭环 (Part 1~4)](#阶段一rag-基石筑基与最小闭环)
  - [阶段二：查询理解与检索前增强 (Part 5~11)](#阶段二查询理解与检索前增强)
  - [阶段三：工业级高级检索与索引优化 (RAG_Techniques 核心)](#阶段三工业级高级检索与索引优化)
  - [阶段四：智能体纠错 RAG 与量化评估门禁 (CRAG & Self-RAG)](#阶段四智能体纠错-rag-与量化评估门禁)
  - [阶段五：终极毕业合体与工程交付](#阶段五终极毕业合体与工程交付)
- [三、 学习进度与打卡验收表](#三-学习进度与打卡验收表)
- [四、 实验环境与工程约定](#四-实验环境与工程约定)

---

## 一、 核心学习原则与能力模型

1. **拒绝黑盒调用，深挖底层数据结构**：每一个概念必须从底层结构（向量多维数组、NumPy 余弦计算、Metadata 字典、RRF 打分算法）讲起，再过渡到 LangChain 生产 API。
2. **复用 LangGraph 既有内功**：充分发挥已掌握的状态机流转、条件路由与 `interrupt()` 优势，直接攻坚业界最顶尖的 **CRAG (纠错 RAG)** 与 **Self-RAG (自省 RAG)**。
3. **每个知识点“三件套”闭环**：
   - **理论拆解**：解决什么经典检索痛点？
   - **独立最小沙盒代码**：独立 `.py` 脚本，几秒内跑通并输出调试指标。
   - **制造失败并修复**：构造反例（如相似度失真、关键词搜不到、表格被切碎），亲手实现优化对比。

---

## 二、 五大演进阶段详细规划

### 阶段一：RAG 基石筑基与最小闭环
> **对标**：`rag-from-scratch` Part 1~4  
> **目标**：搞懂“文字如何变成高维空间向量”，亲手写通“切分 $\rightarrow$ 存库 $\rightarrow$ 检索 $\rightarrow$ 生成”端到端最小闭环。

* **1.1 向量的数学本质与余弦相似度（NumPy 零依赖手算实验）**
  - 文字为什么能算相似度？高维空间向量（Embedding Vector）的物理含义；
  - 编写 15 行纯 Python/NumPy 脚本，手写点积与模长，计算两句话的余弦相似度（Cosine Similarity）；
  - 验证语义联想能力：为什么“出差住五星级超标”与“酒店报销上限规定”在毫无相同字的情况下依然具有 0.85+ 的高相似度？
* **1.2 工业级切分器（Document Chunking）**
  - 核心痛点：整篇规章丢进模型不仅超上下文且浪费 Token，切得太细又会把完整条款截断；
  - 深入掌握 `RecursiveCharacterTextSplitter` 递归切分策略（`\n\n` 段落 $\rightarrow$ `\n` 行 $\rightarrow$ 句号 $\rightarrow$ 标点）；
  - 理解 `chunk_size` 与 `chunk_overlap`（重叠保护窗口，防止关键数字恰好被腰斩切断）。
* **1.3 轻量向量数据库实战（ChromaDB）**
  - 向量数据库的真实内部结构：向量索引（HNSW/ANN）+ 原始文档存根 + Metadata 元数据字典；
  - 最小实验：将 3 篇公司制度存入 Chroma，执行 `similarity_search_with_score` 查看召回片段及真实距离。
* **1.4 最小 RAG 问答链闭环（LCEL 原生管道）**
  - 利用 LangChain LCEL 语法（`retriever | prompt | llm | StrOutputParser`）搭建第一条自动化检索问答链路；
  - 搞懂上下文注入（Context Injection）核心技巧与 System Prompt 防幻觉约束（“只依据参考文档回答，未知请诚实拒答”）。

---

### 阶段二：查询理解与检索前增强
> **对标**：`rag-from-scratch` Part 5~11  
> **目标**：解决“用户问得太口语、太模糊，导致向量库找不到精准条款”的检索前痛点。

* **2.1 多角度改写检索（Multi-Query & RAG-Fusion）**
  - 核心痛点：用户一句话表达有限，直接搜容易漏掉重要条款；
  - 提示词工程：利用大模型将用户提问从 3 个不同的专业视角进行改写扩展；
  - **倒数排名融合（RRF, Reciprocal Rank Fusion）**：多路检索候选段落的数学去重与加权交叉排序，让多路命中的关键条款自动浮到第一位。
* **2.2 假设性文档嵌入（HyDE - Hypothetical Document Embeddings）**
  - 逆向思维：遇到生僻术语或复杂制度问答，先让大模型凭空编写一份“假想答案”；
  - 拿假想答案的向量去搜索知识库，大幅提升冷门条款的语义命中率。
* **2.3 检索智能路由（Query Routing）**
  - 不是所有问题都需要查向量库！
  - 语义路由 vs 逻辑路由：智能体根据意图自动分流（该查规章知识库？该查业务数据库订单表？还是直接走常规问答？）。

---

### 阶段三：工业级高级检索与索引优化
> **对标**：`NirDiamant/RAG_Techniques` 核心精华  
> **目标**：打破“小段落缺上下文，大段落充满噪声”的经典悖论，攻克企业级长文档与发票精准度瓶颈。

* **3.1 混合检索（Hybrid Search: Dense Vector + Sparse BM25）**
  - 痛点：纯向量擅长“意思相近”，但搜“发票代码 1100234”、“增值税专用发票”等精准关键词时经常失灵；
  - 实装 BM25 稀疏检索器（基于字词频率的精确算法），与 Dense 向量检索打通加权融合（RRF），兼具“语义理解”与“一字不差精确搜索”。
* **3.2 父子文档检索（Parent-Document / Small-to-Big Retrieval）**
  - 工业经典模式：切片小了向量检索极准，但喂给模型时因缺上下文而理解片面；
  - 架构设计：切分成 100 字的“子切片”用于向量库高效计算相似度；检索命中后，通过 ID 自动回表调出 1000 字的“整章父文档”注入模型。
* **3.3 语义重排序（Re-ranking with Cross-Encoder）**
  - 向量搜索（Bi-Encoder）为了追求毫秒级吞吐牺牲了精度；
  - 在检索出前 20 条候选段落后，引入专门的 **Reranker 模型**，对这 20 个候选与用户问题做全交叉深度打分，挑选最精确的 Top 3 喂给大模型。

---

### 阶段四：智能体纠错 RAG 与量化评估门禁
> **对标**：`rag-from-scratch` Part 15~18 + LangGraph 状态机融合  
> **目标**：**结合已掌握的 LangGraph 状态机**，打造具备“自查自纠与反思能力”的工业级 Agent。

* **4.1 纠错型 RAG（CRAG - Corrective RAG via LangGraph）**
  - 拓扑设计：检索节点 $\rightarrow$ 判定裁判节点（Document Grader） $\rightarrow$ 条件边；
  - 裁判节点审查检索段落：如果发现搜出的制度和问题不相关，状态机自动走异常分支：重写检索词重搜，或调用搜索引擎兜底。
* **4.2 自我反省 RAG（Self-RAG via LangGraph）**
  - 回答生成后，挂载自我反思裁判：
    - 检查 1（忠实度）：回答的内容是不是完全有据可查？严防模型凭空编造事实；
    - 检查 2（有效度）：回答是否真正解决了用户的原始疑问？
* **4.3 工业级 RAGAS 自动化评测体系**
  - 彻底抛弃“肉眼测试看个大概”的作坊模式；
  - 掌握三大核心指标量化计算：
    - **Faithfulness（忠实度）**：生成文本中有依据的命题占比；
    - **Context Recall（召回率）**：黄金标准答案所需的信息是否全部被检索出来；
    - **Answer Relevance（答案相关度）**：回答与问题的紧扣程度。

---

### 阶段五：终极毕业合体与工程交付
> **目标**：将阶段一到四研发打磨完毕的工业级 RAG 检索器，正式组装为生产微服务工具。

* **5.1 封装为标准 Agent 工具**
  - 将 RAG 管道封装为带有严密异常保护与降级能力的 `@tool` 函数。
* **5.2 融入企业财务差旅合规审计系统**
  - 接入发票报销系统：员工提交酒店发票，RAG 自动在毫秒内准确召回《集团差旅规范》中该职级、该城市的酒店上限，自动比对超标金额，触发后续状态机与主管审批流！

---

## 三、 学习进度与打卡验收表

| 阶段 | 模块 | 核心交付源码 | 状态 |
| :---: | :--- | :--- | :---: |
| **阶段一** | **1.1 向量数学本质** | `lesson_01_cosine_similarity.py` (NumPy 余弦计算实验) | `[x] 已完成` |
| | **1.2 工业文档切分** | `lesson_02_text_chunking.py` (递归切分与重叠对比) | `[x] 已完成` |
| | **1.3 ChromaDB 实战** | `lesson_03_chroma_store.py` (向量持久化与带分检索) | `[x] 已完成` |
| | **1.4 最小 RAG 问答链** | `lesson_04_basic_rag_chain.py` (LCEL 上下文注入闭环) | `[x] 已完成` |
| **阶段二** | **2.1 RAG-Fusion** | `lesson_05_rag_fusion_rrf.py` (多角度查询改写与 RRF 融合) | `[x] 已完成` |
| | **2.2 HyDE 假设检索** | `lesson_06_hyde_retrieval.py` (假想文档生成与特征检索) | `[x] 已完成` |
| | **2.3 检索智能路由** | `lesson_07_query_router.py` (语义与逻辑条件分支路由) | `[x] 已完成` |
| **阶段三** | **3.1 混合检索 BM25** | `lesson_08_hybrid_search.py` (Dense 向量 + BM25 关键词融合) | `[x] 已完成` |
| | **3.2 父子文档检索** | `lesson_09_parent_document.py` (小切片召回，大父段注入) | `[x] 已完成` |
| | **3.3 语义重排序 Rerank** | `lesson_10_cross_encoder_rerank.py` (二阶段 Cross-Encoder 重排) | `[x] 已完成` |
| **阶段四** | **4.1 CRAG 纠错状态机** | `lesson_11_crag_langgraph.py` (LangGraph 动态纠错与降级) | `[x] 已完成` |
| | **4.2 Self-RAG 自省** | `lesson_12_self_rag_reflection.py` (防幻觉自我事实核验) | `[x] 已完成` |
| | **4.3 RAGAS 量化评估** | `lesson_13_ragas_evaluation.py` (忠实度与召回率黄金基准测试) | `[x] 已完成` |
| **阶段五** | **5.1 业务终极合体** | `lesson_17_enterprise_rag_tool.py` (正式注入企业财务审计系统) | `[x] 已完成` |

---

## 四、 实验环境与工程约定

1. **源码存放目录**：统一编写并运行于 `/Users/anan/LearningPython/langChain/`（或新建配套测试目录）。
2. **虚拟环境**：统一使用 `/Users/anan/LearningPython/langGraph/.venv`（已具备完善依赖）。
3. **API 与模型配置**：统一读取项目既有 `.env`：
   - 核心 LLM：DeepSeek-V3 / R1（通过标准 OpenAI 兼容协议调用）；
   - Embedding 向量模型：优先使用 SiliconFlow 硅基流动（如 `BAAI/bge-m3`）或本地快速轻量向量方案。
