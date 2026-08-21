import typer
import httpx

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from tibero_doc.client import TiberoDocClient


console = Console()


def _highlight(text: str, terms: list[str]) -> Text:
    rendered = Text(text)
    lowered = text.lower()
    for term in sorted(set(terms), key=len, reverse=True):
        start = 0
        while term and (position := lowered.find(term.lower(), start)) >= 0:
            rendered.stylize("bold yellow", position, position + len(term))
            start = position + len(term)
    return rendered


def search_command(
    query: str = typer.Argument(
        ...,
        help="검색할 질문 또는 문장",
    ),
    top_k: int = typer.Option(
        5,
        "--top-k",
        "-k",
        help="검색 결과 개수",
    ),
    mode: str = typer.Option("hybrid", "--mode", "-m", help="keyword/vector/graph/hybrid"),
    explain: bool = typer.Option(False, "--explain", help="검색 순위와 유사도 등 기술 정보를 표시합니다."),
):

    client = TiberoDocClient()

    try:

        response = client.search(
            query=query,
            top_k=top_k,
            mode=mode,
        )

    except httpx.ConnectError:

        console.print(
            "[red]API 서버에 연결할 수 없습니다.[/red]"
        )

        raise typer.Exit(1)

    console.print(
        f"\n[bold]Search:[/bold] {query}\n"
    )

    results = response.get(
        "results",
        []
    )

    if not results:

        console.print("[yellow]관련성이 높은 문서를 찾지 못했습니다.[/yellow]")

        return

    for index, result in enumerate(
        results,
        start=1,
    ):

        filename = result.get(
            "filename",
            "-"
        )

        passages = result.get("passages") or [{
            "snippet": result.get("snippet") or result.get("content", ""),
            "chunk_index": result.get("chunk_index"), "page_number": result.get("page_number"),
            "matched_terms": result.get("matched_terms", []),
        }]
        body = Text()
        body.append(f"관련도: {result.get('relevance_label', '보통')}\n", style="bold green")
        if result.get("entities"):
            body.append("관련 엔티티: " + ", ".join(result["entities"][:8]) + "\n", style="dim")
        for passage_index, passage in enumerate(passages, 1):
            location = f"{passage['page_number']}페이지" if passage.get("page_number") else f"청크 {passage.get('chunk_index', '-') }"
            body.append(f"\n근거 {passage_index} · {location}\n", style="bold cyan")
            body.append_text(_highlight(passage.get("snippet", ""), passage.get("matched_terms", [])))
            body.append("\n")
        if explain:
            ranks = [
                f"keyword={result.get('keyword_rank')}" if result.get("keyword_rank") else None,
                f"vector={result.get('vector_rank')}" if result.get("vector_rank") else None,
                f"graph={result.get('graph_rank')}" if result.get("graph_rank") else None,
            ]
            body.append("\n검색 설명: " + ", ".join(rank for rank in ranks if rank), style="dim")
            if result.get("vector_similarity") is not None:
                body.append(f" · 의미 유사도={result['vector_similarity']:.3f}", style="dim")
        body.append(f"\n\n문서 열기: tibero-doc show {result['document_id']}", style="dim")
        console.print(Panel(body, title=f"[bold]{index}. {filename}[/bold]", border_style="cyan"))
