import httpx
import typer
from rich.console import Console

from tibero_doc.client import TiberoDocClient
from tibero_doc.config import load_refresh_token, save_access_token, save_config, save_refresh_token
from rich.table import Table


console = Console()


def invite_command(
    email: str = typer.Argument(...),
    role: str = typer.Option("viewer", "--role", "-r"),
) -> None:
    """현재 워크스페이스로 사용자를 초대합니다."""
    data = TiberoDocClient().invite(email, role)
    console.print("[green]초대를 만들었습니다.[/green]")
    console.print(f"[bold]tibero-doc join {data['invite_token']} --email {email}[/bold]")


def join_command(
    invite_token: str = typer.Argument(...),
    email: str = typer.Option(..., "--email"),
    name: str = typer.Option(..., "--name"),
    server: str | None = typer.Option(None, "--server"),
) -> None:
    """초대 토큰으로 서버와 워크스페이스에 가입합니다."""
    if server:
        save_config(api_url=server)
    client = TiberoDocClient(server)
    try:
        data = client.join(invite_token, email, name)
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]{exc.response.text}[/red]")
        raise typer.Exit(1) from exc
    save_access_token(data["access_token"], client.api_url)
    console.print(f"[green]✓ 가입 완료[/green] workspace={data['workspace_id']}")


def whoami_command() -> None:
    """현재 로그인 사용자와 워크스페이스를 표시합니다."""
    data = TiberoDocClient().me()
    console.print(f"[bold]{data['display_name']}[/bold] <{data['email']}>")
    console.print(f"Role: {data['role']}  Workspace: {data['workspace_id']}")


def login_command(email: str = typer.Option(..., "--email")) -> None:
    """이메일과 비밀번호로 로그인합니다."""
    password = typer.prompt("비밀번호", hide_input=True)
    data = TiberoDocClient().login(email, password)
    save_access_token(data["access_token"])
    save_refresh_token(data["refresh_token"])
    console.print("[green]✓ 로그인했습니다.[/green]")


def refresh_command() -> None:
    """저장된 Refresh Token으로 로그인을 갱신합니다."""
    token = load_refresh_token()
    if not token:
        raise typer.BadParameter("저장된 Refresh Token이 없습니다. login을 먼저 실행하세요.")
    data = TiberoDocClient().refresh(token)
    save_access_token(data["access_token"])
    save_refresh_token(data["refresh_token"])
    console.print("[green]✓ 로그인 세션을 갱신했습니다.[/green]")


def audit_command(limit: int = typer.Option(100, "--limit", "-n")) -> None:
    """현재 워크스페이스의 감사 로그를 조회합니다."""
    rows = TiberoDocClient().audit_logs(limit).get("logs", [])
    table = Table(title="Audit logs")
    for name in ("Time", "Action", "Resource", "Actor"):
        table.add_column(name)
    for row in rows:
        table.add_row(str(row["created_at"]), row["action"], f"{row.get('resource_type')}:{row.get('resource_id')}", str(row.get("actor_user_id")))
    console.print(table)
