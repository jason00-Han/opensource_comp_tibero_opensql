import os
import subprocess
import time

import anyio
import pytest
from mcp import Client


pytestmark = [pytest.mark.integration, pytest.mark.mcp_http]


def test_streamable_http_lists_tools(tmp_path):
    port = os.getenv("MCP_TEST_PORT", "18999")
    process = subprocess.Popen(
        [os.environ.get("PYTHON", os.sys.executable), "-m", "services.mcp_server.main"],
        cwd=os.getcwd(),
        env={
            **os.environ,
            "TIBERO_DOC_DATA_DIR": str(tmp_path),
            "MCP_TRANSPORT": "streamable-http",
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": port,
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        time.sleep(1)

        async def exercise():
            async with Client(f"http://127.0.0.1:{port}/mcp") as client:
                listed = await client.list_tools()
                assert "get_document_stats" in {tool.name for tool in listed.tools}

        anyio.run(exercise)
    finally:
        process.terminate()
        process.wait(timeout=5)
