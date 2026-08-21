import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tibero_doc.client import TiberoDocClient
from tibero_doc.config import get_api_url


console = Console()


def status_command() -> None:
    """API와 OpenSQL의 현재 상태를 표시합니다."""

    api_url = get_api_url()
    console.print(Panel.fit("[bold cyan]Tibero Doc Platform[/bold cyan]", border_style="cyan"))
    try:
        data = TiberoDocClient().health()
    except httpx.ConnectError as exc:
        console.print(f"[red][실패] API 서버에 연결할 수 없습니다: {api_url}[/red]")
        console.print("[cyan]해결: tibero-doc serve[/cyan]")
        console.print("[dim]자세한 진단: tibero-doc doctor[/dim]")
        raise typer.Exit(1) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        try:
            detail = exc.response.json().get("detail", detail)
        except ValueError:
            pass
        console.print(f"[red][실패] API는 실행 중이지만 내부 구성에 문제가 있습니다.[/red]\n{detail}")
        console.print("[cyan]해결: tibero-doc doctor[/cyan]")
        raise typer.Exit(1) from exc

    table = Table(show_header=True, header_style="bold")
    table.add_column("구성 요소")
    table.add_column("상태")
    for name, status in data.get("components", {}).items():
        healthy = status == "healthy"
        # Windows의 기본 CP949 콘솔에서도 깨지지 않는 표기를 사용한다.
        table.add_row(name, "[green]정상[/green]" if healthy else f"[yellow]{status}[/yellow]")
    console.print(table)
    try:
        # /health는 서비스 생존 상태이고, 문서 수는 로그인 워크스페이스 기준으로 표시한다.
        workspace_stats = TiberoDocClient().stats()
    except httpx.HTTPError:
        workspace_stats = data
    database = data.get("database", {})
    console.print(
        f"[dim]DB {database.get('database', '-')} · "
        f"{'Replica' if database.get('is_replica') else 'Primary'} · "
        f"documents {workspace_stats.get('documents', 0)} · chunks {workspace_stats.get('chunks', 0)} · "
        f"embeddings {workspace_stats.get('embeddings', 0)}[/dim]"
    )
