import os
import re

import jieba
import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        port=int(os.getenv("PG_PORT")),
        dbname=os.getenv("PG_DB"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
    )

def run_lesson_p1(query:str)->str:
    """
        将用户自然语言问题通过 jieba 切词，过滤掉标点符号，
        组装为 PostgreSQL to_tsquery 安全可用的 '词1 | 词2 | 词3' 格式
    """
    raw_words = jieba.cut_for_search(query)
    cleaned_tokens = []
    for word in raw_words:
        word =word.strip()
        # 仅保留中文、英文字母和数字，剔除空格与特殊操作符 (& | ! : ( ) 等)，防止 tsquery 语法报错
        if word and re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9]+$", word):
            if word not in cleaned_tokens:
                cleaned_tokens.append(word)
     # 4. 拼接成 PostgreSQL 认识的 tsquery 指令
    return " | ".join(cleaned_tokens)


# print("实验 1：透视 tsvector 与 tsquery 的底层物理结构")
def exp1_inspect_tsvector_and_tsquery():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        raw_Chinese = "外国人来华商务邀请函办理流程"
        jieba_spaced = " ".join(jieba.cut_for_search(raw_Chinese))
        cursor.execute("""
            select
                to_tsvector('simple',%s)::text as without_jieba,
                to_tsvector('simple', %s)::text AS with_jieba,
                to_tsquery('simple','外国人 & 商务 | 签证')::text as query_tree
        """,(raw_Chinese,jieba_spaced)
        )
        no_jieba, with_jieba, q_tree = cursor.fetchone()
        print(f"1. 未分词直接转 tsvector (错误示范):\n   {no_jieba}")
        print(f"2. 经 jieba 分词后转 tsvector (正确示范，注意冒号后的位置编号):\n   {with_jieba}")
        print(f"3. tsquery 编译后的布尔表达式:\n   {q_tree}")

    finally:
        cursor.close()
        conn.close()

def exp2_and_vs_or_recall():
    print("实验 2：布尔算子 & (AND) 与 | (OR) 的召回行为对比")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        doc_tokens = " ".join(jieba.cut_for_search("外国人来华商务邀请函办理流程"))
        query_and = "请问 & 外国人 & 商务"
        query_or = "请问 | 外国人 | 商务"
        cursor.execute("""
        SELECT
                    to_tsvector('simple', %s) @@ to_tsquery('simple', %s) AS match_and,
                    to_tsvector('simple', %s) @@ to_tsquery('simple', %s) AS match_or;
        """,(doc_tokens,query_and, doc_tokens, query_or))
        match_and, match_or = cursor.fetchone()
        print(f"文档分词: {doc_tokens}")
        print(f"使用 [& (AND)] 查询 '{query_and}' 是否命中: {match_and} (因缺少口语词'请问'直接全盘否定！)")
        print(f"使用 [| (OR)]  查询 '{query_or}' 是否命中: {match_or} (成功命中核心词！)")
    finally:
        cursor.close()
        conn.close()

def exp3_ts_rank_cd_cover_density():
    print("实验 3：ts_rank_cd 覆盖密度打分（关键词紧挨 vs 关键词相隔很远）")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        # 文档 A：“商务”和“邀请函”中间隔了很多无关词
        doc_far = "商务 出差 报销 审批 部门 领导 签字 财务 归档 邀请函"
        # 文档 B：“商务”和“邀请函”紧挨在一起
        doc_close = "办理 商务 邀请函 需要 提交 部门 审批 单据 财务 归档"
        query_str = "商务 & 邀请函"
        cursor.execute("""
            select
                ts_rank_cd(to_tsvector('simple',%s),to_tsquery('simple',%s),32) as score_far,
                ts_rank_cd(to_tsvector('simple',%s),to_tsquery('simple',%s),32) as score_close;
        """,(doc_far,query_str,doc_close,query_str))
        score_far, score_close = cursor.fetchone()
        print(f"关键词相隔较远的文档得分 (score_far)  : {score_far:.6f}")
        print(f"关键词紧挨一起的文档得分 (score_close): {score_close:.6f} (因位置紧凑，得分高出数倍！)")
    finally:
        cursor.close()
        conn.close()

def build_safe_or_tsquery(question: str) -> str:
        """
        将用户自然语言问题通过 jieba 切词，过滤掉标点符号，
        组装为 PostgreSQL to_tsquery 安全可用的 '词1 | 词2 | 词3' 格式
        """
        raw_words = jieba.cut_for_search(question)
        clean_tokens = []
        for w in raw_words:
            w = w.strip()
            # 仅保留中文、英文字母和数字，剔除空格与特殊操作符 (& | ! : ( ) 等)，防止 tsquery 语法报错
            if w and re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9]+$", w):
                if w not in clean_tokens:
                    clean_tokens.append(w)
        return " | ".join(clean_tokens)
def exp4_real_kb_chunk_sparse_search():
    conn = get_conn()
    cursor = conn.cursor()
    print("实验 4：在真实 kb.kb_chunk 表上执行 Sparse 全文检索并排出名次")
    try:
        user_question = "请问外国人来华商务邀请函怎么办理？"
        tsquery_str = build_safe_or_tsquery(user_question)
        print(f"用户原始问题: {user_question}")
        print(f"构造 tsquery : {tsquery_str}\n")
        sql="""
            SELECT                                                                                                   
                    c.id AS chunk_id,
                    c.metadata ->> 'file_name' AS file_name,
                    ROUND(ts_rank_cd(c.tsv_content, to_tsquery('simple', %s))::numeric, 6) AS sparse_score,
                    ROW_NUMBER() OVER (
    			ORDER BY ts_rank_cd(c.tsv_content, to_tsquery('simple', %s)) DESC
                    ) AS rank_s,
                    LEFT(REPLACE(c.content, E'\n', ' '), 60) AS content_preview
                FROM kb.kb_chunk c
                JOIN kb.kb_file f ON c.file_id = f.id
                WHERE f.delete_flag = FALSE
    		  AND c.tsv_content @@ to_tsquery('simple', %s)
                ORDER BY sparse_score DESC
                LIMIT 5;
        """
        cursor.execute(sql, (tsquery_str, tsquery_str, tsquery_str))
        rows = cursor.fetchall()
        if not rows:
            print("未检索到匹配切片（请确认相关文件已在控制台入库，或更换已入库文件的关键词测试）。")
        for r in rows:
            chunk_id, fname, score, rank_s, preview = r
            print(f"[第 {rank_s} 名] 切片ID: {chunk_id:<4} | 得分: {score:<8} | 来源: {fname}\n   摘要: {preview}...")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    res = run_lesson_p1("明天你好，你爱哪里，i我在找你，")
    print(res)
    # exp1_inspect_tsvector_and_tsquery()
    # exp2_and_vs_or_recall()
    # exp3_ts_rank_cd_cover_density()
    exp4_real_kb_chunk_sparse_search()

