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
):

    client = TiberoDocClient()

    try:

        response = client.search(
            query=query,
            top_k=top_k,
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

        console.print(content)

        console.print()