from langchain_core.tools import tool


@tool("web_search",description="这是一个网页搜索工具")  # Custom name
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

print(search.name)  # web_search