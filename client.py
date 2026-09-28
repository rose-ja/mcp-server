from __future__ import annotations

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

    async with stdio_client(server_parameters) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_result = await session.list_tools()

            print("Discovered tools:")
            for tool in tools_result.tools:
                print(f"- {tool.name}")

            list_result = await session.call_tool(
                "list_directory",
                {"path": "."},
            )
            print("\nList directory:")
            print(list_result.content)

            read_result = await session.call_tool(
                "read_file",
                {"path": "README.md"},
            )
            print("\nRead file:")
            print(read_result.content)

            write_result = await session.call_tool(
                "write_file",
                {
                    "path": "notes.txt",
                    "content": "created by MCP client\n",
                },
            )
            print("\nWrite file:")
            print(write_result.content)

            search_result = await session.call_tool(
                "search_files",
                {
                    "query": "MCP",
                    "path": ".",
                },
            )
            print("\nSearch files:")
            print(search_result.content)

            traversal_result = await session.call_tool(
                "read_file",
                {"path": "../secret.txt"},
            )
            print("\nTraversal attempt:")
            print(traversal_result.content)

if __name__ == "__main__":
    asyncio.run(main())