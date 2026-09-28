import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).with_name("server.py")

async def main() -> None:
    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
    )
    
    async with stdio_client(server_parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # MCP 要求先完成初始化握手，再调用 tools/list 或 tools/call。
            await session.initialize()
            
            resources_result = await session.list_resources()
            
            print("\nDiscovered resources:")
            for resource in resources_result.resources:
                print(f"- {resource.uri}: {resource.name}")

            resource_result = await session.read_resource("workspace://project-info")

            print("\nResource result:")
            print(resource_result.contents)

            # 阶段一：发现 Server 暴露的工具。
            tools_result = await session.list_tools()
            
            print("Discovered tools:")
            for tool in tools_result.tools:
                print(f"- {tool.name}: {tool.description}")
                
            # 阶段二：调用已经发现的工具。
            result = await session.call_tool(
                "describe_path",
                {"path": "src/index.ts"},
            )

            print("\nNormal call result:")
            print(result.content)
            
            # 传入空路径，观察 Server 的参数校验错误。
            invalid_result = await session.call_tool(
                "describe_path",
                {"path": ""},
            )

            print("\nEmpty path result:")
            print(invalid_result.content)
    
    

if __name__ == "__main__":
    asyncio.run(main())