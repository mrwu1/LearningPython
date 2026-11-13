from typing import TypedDict, Annotated

from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger

from lesson_03_chroma_store import VectorRecord
from utils.model import get_llm

#  Pydantic BaseModel 区别：取值方式不一样，pydantic是实例对象
class MultiQueryOutput(TypedDict):

    queries:Annotated[list[str],"从三个不同规章维度拆解改写后的专业检索子查询列表"]

# 1. 调用model,生成 三个不同角度的问题
def generate_queries(query:str)->list[str]:
    """
    第 1 步 (Multi-Query)：调用 LLM 将用户的口语化/复合问题拆解改写为 3 个独立的专业检索词
    """
    system_prompt="""你是一位企业差旅制度检索专家。
    用户的原始提问可能比较口语化，或者一句话里面包含了多个报销场景（如同时问了住宿、打车，周末餐饮等）。
    请将用户的原始问题拆解，改写为三个不同维度、用词专业精准的独立检索子查询，以便在规章知识库中全面召回相关条款。
    """
    llm=get_llm()
    llm_width_structure = llm.with_structured_output(schema=MultiQueryOutput,method ="function_calling")

    res = llm_width_structure.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"用户原始问题：{query}")
        ]
    )
    logger.info(f"res: {res}")
    return res["queries"]

# 2.倒数排名
#     doc_id:str
#     document:str
#     embedding:list[float]
#     metadata:dict[str,Any] = field(default_factory=dict)
# 60 - 也是 2009 年滑铁卢大学发表 RRF 原始论文时经过上万次实验定下来的全球通用标准常数
def reciprocal_rank_fusion(
        ranked_list:list[list[VectorRecord]],
        k:int=60
)->list[tuple[VectorRecord,float]]:
    """
    第 2 步 (RRF 核心算法)：倒数排名融合
    公式: RRF_Score(doc) = sum( 1.0 / (k + rank) )，其中 rank 从 1 开始计。
    作用: 自动去重，并将多路检索均名列前茅的“共识文档”推向榜首！
    """
    rrf_scores:dict[str,float]= {}
    doc_map:dict[str,VectorRecord]= {}
    for single_list in ranked_list:
        for rank,record in enumerate(single_list,1):
            doc_id = record.doc_id
            doc_map[doc_id] = record
            # 核心累加公式：原来得过的分 + 当前这一路的名次倒数分 {"doc_id1: 13,"doc_id2: 4}
            rrf_scores[doc_id] = rrf_scores.get(doc_id,0)+(1.0/(k+rank))
    # 按累加后的 RRF 总分从高到低排序
    sorted_doc_ids =  sorted(
        rrf_scores.keys(),
        key=lambda did: rrf_scores[did],
        reverse=True
    )
    #ex: ["doc_id1","doc_id2"]
    return [(doc_map[did], rrf_scores[did]) for did in sorted_doc_ids]

if __name__=="__main__":
    # 1. 测试大模型多视角查询改写 (Multi-Query)
    raw_q = "我周六去上海赶项目，打车去现场和晚上加班吃饭怎么报销？"
    print(f"🗣️ 用户原始复合提问: {raw_q}\n")
    sub_queries = generate_queries(raw_q)
    print("🤖 DeepSeek 拆解改写出的 3 个专业检索词:")
    for idx,sq in enumerate(sub_queries,1):
        print(f"   子查询 {idx}: {sq}")

    # ❌：中间步骤：本来应该拿着这 3 个子查询，去第 3 课的向量数据库 kb 里分别搜 3 次！

    # 2. 验证 RRF 倒数排名融合算法
        #     doc_id:str
        #     document:str
        #     embedding:list[float]
        #     metadata:dict[str,Any] = field(default_factory=dict)
    doc_taxi = VectorRecord("DOC-TAXI", "工作日及出差市内打车每日上限150元", [])
    doc_meal = VectorRecord("DOC-MEAL", "周末加班餐饮上限150元，须附OA加班审批单", [])
    doc_hotel = VectorRecord("DOC-HOTEL", "上海超一线城市初级员工住宿上限450元/晚", [])
    doc_flight = VectorRecord("DOC-FLIGHT", "初级员工城际高铁/机票单程上限1000元", [])
    # 模拟 3 个子查询各自从向量库召回的 Top-3 排名列表
    #问题❓：  这 3 份成绩单加起来一共有 3 × 3 = 9 个文档，
    #           里面有大量重复（比如 doc_taxi 出现了 3 次），而且在每份成绩单里的名次都不一样！
    retrieved_lists = [
        [doc_taxi, doc_flight, doc_hotel],  # 子查询1(交通视角) 的召回排名: #1打车, #2机票, #3酒店
        [doc_meal, doc_taxi, doc_hotel],  # 子查询2(周末餐饮视角) 的召回排名: #1餐饮, #2打车, #3酒店
        [doc_hotel, doc_meal, doc_taxi],  # 子查询3(上海差旅视角) 的召回排名: #1酒店, #2餐饮, #3打车
    ]
    print("🏆 RRF (k=60) 倒数排名融合去重后的最终结果:")
    # ✅：这就是第 91 行 reciprocal_rank_fusion(retrieved_lists, k=60) 要测的 两件事：
    #  #### 1. 测“自动去重”（通过 doc_map 字典）：
    #  #### 2. 测“按名次倒数累加计分”（通过 rrf_scores 字典）：
    fused_results = reciprocal_rank_fusion(retrieved_lists, k=60)
    for final_rank,(rec,rrf_score) in enumerate(fused_results,1):
        print(f"最终排名 #{final_rank} | RRF得分: {rrf_score:.6f} | [{rec.doc_id}] {rec.document}")