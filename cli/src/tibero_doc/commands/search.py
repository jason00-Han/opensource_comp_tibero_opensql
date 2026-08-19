import typer
import httpx

from rich.console import Console

from tibero_doc.client import TiberoDocClient


console = Console()


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

        console.print(
            "[yellow]검색 결과가 없습니다.[/yellow]"
        )

        return

    for index, result in enumerate(
        results,
        start=1,
    ):

        score = result.get(
            "score",
            0,
        )

        content = result.get(
            "content",
            "",
        )

        filename = result.get(
            "filename",
            "-"
        )

        console.print(
            f"[bold cyan]{index}. {filename}[/bold cyan]"
        )

        console.print(
            f"Score: {score:.4f}"
        )

        ranks = [
            f"keyword={result.get('keyword_rank')}" if result.get("keyword_rank") else None,
            f"vector={result.get('vector_rank')}" if result.get("vector_rank") else None,
            f"graph={result.get('graph_rank')}" if result.get("graph_rank") else None,
        ]
        console.print("Ranks: " + ", ".join(rank for rank in ranks if rank))
        if result.get("entities"):
            console.print("Entities: " + ", ".join(result["entities"]))

        console.print(content)

        console.print()
