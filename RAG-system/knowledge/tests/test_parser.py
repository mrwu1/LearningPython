from app.parsers.document_parser import DocumentParser


def run_parser_test():
    print("开始测试 DocumentParser 异构文档流式解析器...")
    parse = DocumentParser(chunk_size=400,chunk_overlap=80)
    # 1. 抽取 kb_file.sql 中的一个真实 Word 规章文件进行测试
    test_word_url =(
        "https://geo-test-1327559436.cos.ap-guangzhou.myqcloud.com/temp/20260901/c56de039-45fa-4151-b1d1-3b331e1e9a30/%E6%B3%A2%E5%85%B0%E5%9B%BD%E5%88%AB%E7%AD%BE%E8%AF%81%E8%A1%A8-%E5%8C%97%E4%BA%AC%E4%B8%8A%E6%B5%B7%E9%A2%86%E5%8C%BA-Country-Visa-Application-Form-Beijing-Consular-District.docx"
    )
    test_word_name = "波兰国别签证表.docx"
    result = parse.parse_from_cos(
        url=test_word_url,
        file_id=224178508660737,
        file_name=test_word_name,
        file_ext="docx"
    )
    print(f"1. 成功解析文件: {result.file_name}")
    print(f"2. 提取字符总数: {result.raw_char_count}")
    print(f"3. 产出切片数量: {len(result.chunks)}")
    assert len(result.chunks) > 0, "切片数量不应为 0"

    # 打印前 2 个切片的头部与分词样本
    first_chunk = result.chunks[0]
    print("\n--- 首个切片正文前 120 字符 ---")
    print(first_chunk.content[:120])
    print("--- 首个切片 jieba 检索词串 (前 60 字符) ---")
    print(first_chunk.jieba_tokens[:60])

    # 验证关键字段契约
    assert first_chunk.content.startswith("【制度来源：波兰国别签证表.docx】")
    assert len(first_chunk.jieba_tokens) > 0
    assert first_chunk.metadata["file_id"] == 224178508660737

if __name__ == "__main__":
    run_parser_test()