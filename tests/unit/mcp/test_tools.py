import pytest

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from services.mcp_server.service import MCPDocumentService


pytestmark = pytest.mark.unit


def test_tools_search_status_and_stats(tmp_path):
    documents = DocumentStore(tmp_path)
    documents.ingest_bytes("guide.txt", b"MCP searchable document")
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.SYNC_DOCUMENTS, {})
    tools = MCPDocumentService(documents, jobs)
    assert tools.search("searchable")["results"][0]["filename"] == "guide.txt"
    assert tools.job_status(job.job_id)["status"] == "queued"
    assert tools.stats() == {"documents": 1, "chunks": 1}


@pytest.mark.parametrize("query,top_k", [("", 5), ("valid", 0), ("valid", 101)])
def test_search_tool_validation(tmp_path, query, top_k):
    with pytest.raises(ValueError):
        MCPDocumentService(DocumentStore(tmp_path), JsonJobRepository(tmp_path)).search(query, top_k)
