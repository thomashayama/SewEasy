# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==1.30.0", "httpx>=0.28,<1"]
# ///
"""Stdio bridge for desktop MCP clients; no SewEasy drafting dependencies needed.

Run: uv run integrations/seweasy_mcp.py
Environment: SEWEASY_TOKEN, optional SEWEASY_URL (the web app's origin).
"""
import asyncio
import os
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server


async def main():
    token = os.environ.get('SEWEASY_TOKEN', '')
    origin = os.environ.get('SEWEASY_URL', 'https://seweasy.thomashayama.com').rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('SEWEASY_URL must use HTTPS, except for localhost development.')
    if not token:
        raise ValueError('Set SEWEASY_TOKEN using Account → Agent connections in SewEasy.')
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token}, timeout=180) as http:
        async with streamable_http_client(origin + '/mcp/', http_client=http) as (read, write, _):
            async with ClientSession(read, write) as remote:
                info = await remote.initialize()
                server = Server('SewEasy', instructions=info.instructions)

                @server.list_tools()
                async def list_tools():
                    return (await remote.list_tools()).tools

                @server.call_tool()
                async def call_tool(name, arguments):
                    return await remote.call_tool(name, arguments)

                @server.list_resources()
                async def list_resources():
                    return (await remote.list_resources()).resources

                @server.read_resource()
                async def read_resource(uri):
                    result = await remote.read_resource(uri)
                    return [ReadResourceContents(content=c.text, mime_type=c.mimeType) for c in result.contents]

                async with stdio_server() as (incoming, outgoing):
                    await server.run(incoming, outgoing, server.create_initialization_options())


if __name__ == '__main__':
    asyncio.run(main())
