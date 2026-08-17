import json
import os

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from services.api.store import DocumentStore


pytestmark = pytest.mark.integration


def test_stdio_server_lists_tools_and_searches(tmp_path):
    DocumentStore(tmp_path).ingest_bytes("stdio.txt", b"stdio MCP transport search")
    params = StdioServerParameters(
        command=os.environ.get("PYTHON", os.sys.executable),
        args=["-m", "services.mcp_server.main"],
        cwd=str(os.getcwd()),
        env={**os.environ, "TIBERO_DOC_DATA_DIR": str(tmp_path), "MCP_TRANSPORT": "stdio"},
    )

    async def exercise():
        async with Client(stdio_client(params)) as client:
            listed = await client.list_tools()
            assert "search_documents" in {tool.name for tool in listed.tools}
            result = await client.call_tool("search_documents", {"query": "transport", "top_k": 3})
            assert json.loads(result.content[0].text)["results"][0]["filename"] == "stdio.txt"

    anyio.run(exercise)
