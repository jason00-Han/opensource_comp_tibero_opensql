from __future__ import annotations

import os

from mcp.server import MCPServer

from services.mcp_server.service import MCPDocumentService
from services.api.auth import authenticate
from packages.core.database import database_dsn


server = MCPServer("Tibero Doc")
access_token = os.getenv("TIBERO_DOC_ACCESS_TOKEN")
if database_dsn() and os.getenv("AUTH_MODE", "required") == "required" and not access_token:
    raise RuntimeError("TIBERO_DOC_ACCESS_TOKEN is required for MCP access")
context = authenticate(f"Bearer {access_token}") if access_token else None
documents = MCPDocumentService(context=context)


@server.tool()
def search_documents(query: str, top_k: int = 5) -> dict:
    """Search indexed documents using keyword and vector retrieval."""
    return documents.search(query, top_k)


@server.tool()
def list_documents(limit: int = 100, offset: int = 0) -> dict:
    """List indexed documents and their metadata."""
    return documents.list_documents(limit, offset)


@server.tool()
def get_document(document_id: str) -> dict:
    """Return one document, metadata and all indexed chunks."""
    return documents.get_document(document_id)


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
