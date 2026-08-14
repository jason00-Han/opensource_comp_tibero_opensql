from __future__ import annotations

import os

from mcp.server import MCPServer

from services.mcp_server.service import MCPDocumentService


server = MCPServer("Tibero Doc")
documents = MCPDocumentService()


@server.tool()
def search_documents(query: str, top_k: int = 5) -> dict:
    """Search indexed document chunks using synchronous keyword search."""
    return documents.search(query, top_k)


@server.tool()
def get_job_status(job_id: str) -> dict:
    """Return pipeline status and result for an ingest, embedding, or sync job."""
    return documents.job_status(job_id)


@server.tool()
def get_document_stats() -> dict:
    """Return indexed document and chunk counts."""
    return documents.stats()


def run_server() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        server.run(
            transport=transport,
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "8001")),
        )
    else:
        server.run(transport=transport)


if __name__ == "__main__":
    run_server()
