from pathlib import Path

import typer
import httpx

from rich.console import Console

from tibero_doc.client import TiberoDocClient


console = Console()


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".html",
}


def ingest_command(
    path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="업로드할 문서 또는 디렉터리",
    )
):

    client = TiberoDocClient()

    if path.is_file():

        files = [path]

    else:

        files = [
            file
            for file in path.rglob("*")
            if (
                file.is_file()
                and file.suffix.lower()
                in SUPPORTED_EXTENSIONS
            )
        ]

    if not files:

        console.print(
            "[yellow]지원되는 문서를 찾지 못했습니다.[/yellow]"
        )

        return

    console.print(
        f"\n[bold]{len(files)} documents discovered[/bold]\n"
    )

    success = 0

    for file in files:

        try:

            client.ingest(file)

            console.print(
                f"[green]✓[/green] {file.name}"
            )

            success += 1

        except httpx.HTTPError as e:

            console.print(
                f"[red]✗[/red] {file.name} - {e}"
            )

    console.print()

    console.print(
        f"[green]{success}[/green]"
        f"/{len(files)} documents uploaded"
    )