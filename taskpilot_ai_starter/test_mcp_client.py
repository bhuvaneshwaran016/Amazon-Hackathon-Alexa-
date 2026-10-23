import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    url = "http://127.0.0.1:8001/mcp"
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            print("MCP connection successful!")
            print("Available tools:")
            for tool in result.tools:
                print("-", tool.name)

asyncio.run(main())

