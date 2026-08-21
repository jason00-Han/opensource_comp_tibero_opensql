import json

import httpx
import typer
from rich.console import Console
from rich.table import Table

from tibero_doc.client import TiberoDocClient


console = Console()


def list_command(limit: int = typer.Option(100, "--limit", "-n")) -> None:
    data = TiberoDocClient().documents(limit)
    table = Table(title="Indexed documents")
    for column in ("ID", "Filename", "Version", "Chunks", "Bytes"):
        table.add_column(column)
    for item in data.get("documents", []):
        table.add_row(item["document_id"], item["filename"], str(item.get("version", 1)), str(item.get("chunk_count", 0)), str(item.get("size", 0)))
    console.print(table)


def show_command(document_id: str) -> None:
    try:
        data = TiberoDocClient().document(document_id)
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]{exc.response.text}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


def delete_command(document_id: str, yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    if not yes and not typer.confirm(f"Delete document {document_id}?"):
        raise typer.Abort()
    TiberoDocClient().delete_document(document_id)
    console.print(f"[green]Deleted {document_id}[/green]")


def versions_command(document_id: str) -> None:
    data = TiberoDocClient().versions(document_id)
    table = Table(title=f"Versions: {data['filename']}")
    for column in ("Version", "Document ID", "Checksum", "Created"):
        table.add_column(column)
    for item in data.get("versions", []):
        table.add_row(str(item["version"]), item["document_id"], item["checksum"][:12], str(item.get("created_at", "-")))
    console.print(table)


def job_command(job_id: str) -> None:
    data = TiberoDocClient().job(job_id)
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


def graph_command(document_id: str) -> None:
    """문서에서 추출된 엔티티와 관계를 조회합니다."""
    data = TiberoDocClient().document_graph(document_id)
    console.print_json(json.dumps(data, ensure_ascii=False, default=str))


def graph_reindex_command() -> None:
    """현재 워크스페이스의 기존 문서를 지식 그래프로 다시 색인합니다."""
    data = TiberoDocClient().reindex_graph()
    console.print(f"[green]{data['documents']}개 문서의 지식 그래프 색인을 완료했습니다.[/green]")


def embedding_reindex_command() -> None:
    """현재 의미 모델로 기존 문서 임베딩을 다시 생성합니다."""
    data = TiberoDocClient().reindex_embeddings()
    action = "작업을 큐에 등록" if data.get("queued") else "색인을 완료"
    console.print(f"[green]{data['documents']}개 문서의 {data['model']} 임베딩 {action}했습니다.[/green]")
