CORPORATE_POLICY_TEXT = """【第一章：住宿报销规范】                                                                  
    第一条：超一线城市（北京、上海、广州、深圳）住宿标准：初级员工(JUNIOR)上限450元/晚，资深员工(SENIOR)上限650元/晚，经 
    理(MANAGER)上限900元/晚。                                                                                            
    第二条：普通城市住宿标准：初级员工上限350元/晚，资深员工上限500元/晚。                                               

    【第二章：餐饮与加班红线】                                                                                           
    第三条：工作日误餐补助上限为100元/天。周末餐饮报销上限为150元/天，但必须附带OA系统审批通过的加班单；若周末无加班审批 
    单，一律视为私费公报，严禁报销！"""

def naive_fixed_chunking(text:str,chunk_size:int)->list[str]:
    """
            ❌ 反例：无重叠定长硬切 (chunk_overlap = 0)
            直接按固定长度切分，极易把“城市/职级”与“金额数字”从中间劈成两半！
    """
    return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)]

# 第二种
def sliding_window_chunking(text:str,chunk_size:int,chunk_overlap:int)->list[str]:
    """
           ✅ 修复 1：带重叠保护窗口的滑动切分
           核心公式：每次前进的步长 step = chunk_size - chunk_overlap
    """
    if chunk_overlap>=chunk_size:
        raise ValueError('❌chunk_overlap must be less than chunk_size')
    step = chunk_size - chunk_overlap
    chunks=[]
    # 从 start 开始，每次加 step，直到不满足 < stop（step 为负时是 > stop）
    for i in range(0,len(text),step): # 25
        chunk = text[i:i+chunk_size]
        chunks.append(chunk)
        # ‼️：i = 0、i = 25、i = 50，i= 75
        if i+ chunk_size>len(text):
            break
    return chunks

# 第三种
def recursive_semantic_chunking(
            text: str,
            chunk_size: int,
            separators: list[str] = ["\n\n", "\n", "。", "；", ""],
    ) -> list[str]:
        """
        ✅ 修复 2：白盒实现 RecursiveCharacterTextSplitter 核心递归算法
        优先按大段落(\n\n)切 -> 超长再按行(\n)切 -> 再按句号(。)切，绝不在句子中间乱砍！
        """
        # 基准情况：如果当前文本已经小于等于 chunk_size，无需再切，直接返回
        if len(text) <= chunk_size or not separators:
            return [text.strip()] if text.strip() else []

        # 找到第一个在文本中实际存在的分隔符
        current_sep = separators[0] # "\n\n"
        next_separators = separators[1:] # [ "\n", "。", "；", ""] 从第一个开始，直到最后

        if current_sep == "":
            # 兜底：按字符硬切
            return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)]

        if current_sep not in text:
            # 当前分隔符不存在，递归尝试下一级更细的分隔符
            return recursive_semantic_chunking(text, chunk_size, next_separators)

        # 按当前分隔符切开，并对仍然超长的子块递归调用下一级分隔符
        final_chunks = []
        raw_splits = text.split(current_sep) # 切片
        current_buf = ""

        for piece in raw_splits:
            if not piece.strip(): # 去除 首尾 的 空格、`\n`、`\t` 等
                continue
            # 补回句号等有意义的标点
            piece_with_sep = piece + (current_sep if current_sep in ("。", "；") else "")

            # 如果合并后不超过 chunk_size，则攒在一起
            candidate = f"{current_buf}{current_sep if current_buf and current_sep in ('\n\n', '\n') else
            ''}{piece_with_sep}"
            if len(candidate) <= chunk_size:
                current_buf = candidate
            else:
                # 装满一箱，搬上truck一箱
                if current_buf:
                    final_chunks.append(current_buf.strip())
                    # 如果单个 piece 本身就超过了 chunk_size，继续往下一级分隔符递归切分！
                if len(piece_with_sep) > chunk_size:
                    final_chunks.extend(
                        recursive_semantic_chunking(piece_with_sep, chunk_size, next_separators)
                    )
                    current_buf = ""
                else:
                    current_buf = piece_with_sep

        if current_buf.strip():
            final_chunks.append(current_buf.strip())

        return final_chunks
if __name__ == '__main__':
    print("❌ 实验 1：无重叠硬切 (chunk_size=40, overlap=0) —— 观察金额是如何被腰斩的：")
    res1 = naive_fixed_chunking(CORPORATE_POLICY_TEXT,40)
    for idx,chunk in enumerate(res1,1):
        print(f"[Chunk {idx:02d}] ({len(chunk)}字): {repr(chunk)}")

    print("✅ 实验 2：滑动窗口重叠切分 (chunk_size=40, overlap=15) —— 接缝处信息得以保留：")
    res2 = sliding_window_chunking(CORPORATE_POLICY_TEXT,40,15)
    for idx,chunk in enumerate(res2,1):
        print(f"[Chunk {idx:02d}] ({len(chunk)}字): {repr(chunk)}")

    print("🏆 实验 3：递归语义边界切分 (chunk_size=90) —— 严格按章节/条款/句号优雅切分：")
    res3 = recursive_semantic_chunking(CORPORATE_POLICY_TEXT,90)
    for idx,chunk in enumerate(res3,1):
        print(f"[Chunk {idx:02d}] ({len(chunk)}字):\n{chunk}\n" + "-" * 40)