from mcp.server.mcpserver import MCPServer

mcp = MCPServer("filesystem-learning-demo")

@mcp.tool()
def describe_path(path: str) -> str:
    """返回传入路径的描述，不访问真实文件。"""
    normalized_path = path.strip()
    
    if not normalized_path:
        raise ValueError("path must not be empty")

    return f"received path: {normalized_path}"

if __name__ == "__main__":
    # stdio 模式下，协议消息通过标准输入输出传输。
    # 不要在这里使用 print 输出调试信息，否则可能污染 MCP 协议流。
    mcp.run(transport="stdio")