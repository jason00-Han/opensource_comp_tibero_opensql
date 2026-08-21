import typer
from rich.console import Console

from tibero_doc.config import save_config

console = Console()

def init_command(
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="Tibero Doc API 서버 주소",
    )
):
    """
    Tibero Doc CLI 환경을 초기화합니다.
    """

    save_config(api_url)

    console.print(
        "[green]✓ Tibero Doc initialized[/green]"
    )

    console.print(
        f"API Server: [cyan]{api_url}[/cyan]"
    )