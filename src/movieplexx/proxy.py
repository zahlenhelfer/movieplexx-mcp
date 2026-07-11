"""Local stdio<->HTTP proxy: bridges a Claude Code stdio client to the
remote Streamable-HTTP MCP server, attaching the bearer token so the client
config only has to carry `MCP_AUTH_TOKEN` instead of a hand-built header.
"""

from __future__ import annotations

import logging
import os

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

log = logging.getLogger("movieplexx")


async def run_proxy(url: str) -> None:
    token = os.environ.get("MCP_AUTH_TOKEN")
    if not token:  # fail-closed, mirrors the http-transport server side
        raise SystemExit("MCP_AUTH_TOKEN is required for `movieplexx connect`")
    headers = {"Authorization": f"Bearer {token}"}

    log.info("connecting to remote MCP server at %s", url)
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as remote:
            await remote.initialize()

            local = Server("movieplexx-proxy")

            @local.list_tools()
            async def _list_tools():
                return (await remote.list_tools()).tools

            @local.call_tool()
            async def _call_tool(name: str, arguments: dict):
                result = await remote.call_tool(name, arguments)
                return result.content, result.structuredContent

            log.info("serving MCP over stdio, proxied to %s", url)
            async with stdio_server() as (in_stream, out_stream):
                await local.run(in_stream, out_stream,
                                 local.create_initialization_options())
