import os
from typing import Any
from pathlib import Path

def print_graph_mermaid(graph: Any,graph_name: str, save_png: bool = False, save_mmd: bool = True):
    """
    通用LangGraph绘图工具
    :param graph: builder.compile()编译后的graph实例
    :param save_png: 是否导出png图片
    :param save_mmd: 是否自动生成graph.mmd文件到项目根目录
    """
    if os.getenv("ENV", "dev") != "dev":
        return
    graph_def = graph.get_graph()
    mmd_code = graph_def.draw_mermaid()

    # print on the console
    # print("\n===== 📊 LangGraph Mermaid workflow =====")
    # print(mmd_code)
    # print("=======================================\n")

    # ✅ generate a .mmd file automatically
    if save_mmd:
        Path(f"graph_{graph_name}.mmd").write_text(mmd_code, encoding="utf-8")
        print("✅ mermaid has been generated successful：graph.mmd")

    if save_png:
        png_bytes = graph_def.draw_mermaid_png()
        with open(f"graph_out_{graph_name}.png", "wb") as f:
            f.write(png_bytes)
        print("✅ name of the workflow png is called：graph_out.png")
    return mmd_code
