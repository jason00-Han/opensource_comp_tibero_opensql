import json

import typer
from rich.console import Console

from tibero_doc.config import CONFIG_FILE, delete_password, load_config


console = Console()
settings_app = typer.Typer(help="저장된 실행 설정을 확인하거나 초기화합니다.")


@settings_app.command("show")
def show_settings() -> None:
    """비밀번호를 제외한 현재 설정을 표시합니다."""
    console.print_json(json.dumps(load_config(), ensure_ascii=False, indent=2))
    console.print(f"[dim]{CONFIG_FILE}[/dim]")


@settings_app.command("path")
def settings_path() -> None:
    console.print(str(CONFIG_FILE))


@settings_app.command("reset")
def reset_settings(yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    if not yes and not typer.confirm("Tibero Doc 설정을 초기화할까요?"):
        raise typer.Abort()
    config = load_config()
    delete_password(config)
    CONFIG_FILE.unlink(missing_ok=True)
    console.print("[green]설정을 초기화했습니다.[/green]")
