from __future__ import annotations

import os
import socket
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tibero_doc.config import (
    CONFIG_FILE,
    build_dsn,
    load_config,
    load_password,
    runtime_environment,
    save_access_token,
    save_config,
    save_password,
)


console = Console()


def _tcp_check(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "연결됨"
    except OSError as exc:
        return False, str(exc)


def _database_check(dsn: str) -> tuple[bool, str]:
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=4) as connection:
            database, replica = connection.execute(
                "SELECT current_database(), pg_is_in_recovery()"
            ).fetchone()
        return True, f"{database} / {'Replica' if replica else 'Primary'}"
    except Exception as exc:
        return False, str(exc)


def _confirmed_password(label: str, attempts: int = 3) -> str:
    """Typer의 모호한 기본 확인 문구 대신 명확한 두 프롬프트를 사용한다."""
    for attempt in range(1, attempts + 1):
        password = typer.prompt(label, hide_input=True)
        confirmation = typer.prompt(f"{label} 확인", hide_input=True)
        if password and password == confirmation:
            return password
        console.print(
            f"[red]두 비밀번호가 일치하지 않습니다. ({attempt}/{attempts})[/red]"
        )
    console.print("[red]비밀번호 확인에 반복해서 실패하여 설정을 중단합니다.[/red]")
    raise typer.Exit(1)


def setup_command() -> None:
    """대화형 마법사로 OpenSQL과 API 실행 환경을 설정합니다."""

    current = load_config()
    console.print(
        Panel.fit(
            "[bold cyan]Tibero Doc 시작 마법사[/bold cyan]\n"
            "환경 변수와 URL 인코딩을 직접 다루지 않아도 됩니다.",
            border_style="cyan",
        )
    )
    api_url = typer.prompt("API 주소", default=current["api_url"])
    db_host = typer.prompt("OpenProxy 호스트", default=current["db_host"])
    db_port = typer.prompt("OpenProxy 포트", default=current["db_port"], type=int)
    db_user = typer.prompt("DB 사용자", default=current["db_user"])
    db_name = typer.prompt("OpenProxy 풀 이름", default=current["db_name"])
    data_dir = typer.prompt("문서 저장 경로", default=current["data_dir"])
    pipeline_mode = typer.prompt(
        "문서 처리 방식 (queue/inline)", default=current["pipeline_mode"]
    ).strip().lower()
    if pipeline_mode not in {"queue", "inline"}:
        raise typer.BadParameter("문서 처리 방식은 queue 또는 inline이어야 합니다.")
    embedding_provider = typer.prompt(
        "임베딩 방식 (local/ollama/openai)", default=current["embedding_provider"]
    )
    embedding_model = typer.prompt("임베딩 모델", default=current["embedding_model"])

    candidate = dict(current)
    candidate.update(
        api_url=api_url,
        db_host=db_host,
        db_port=db_port,
        db_user=db_user,
        db_name=db_name,
        data_dir=str(Path(data_dir).expanduser()),
        pipeline_mode=pipeline_mode,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )

    tcp_ok, tcp_detail = _tcp_check(str(db_host), int(db_port))
    if not tcp_ok:
        console.print(f"[red]OpenProxy에 연결할 수 없습니다: {tcp_detail}[/red]")
        console.print("OpenSQL/OpenProxy를 시작한 뒤 `tibero-doc setup`을 다시 실행하세요.")
        raise typer.Exit(1)

    console.print(
        "[dim]아래 값은 기존 OpenSQL postgres 계정의 비밀번호입니다. "
        "여기서 새 DB 비밀번호가 설정되지는 않습니다.[/dim]"
    )
    password = ""
    db_ok = False
    db_detail = ""
    for attempt in range(1, 4):
        password = typer.prompt("OpenSQL postgres 비밀번호", hide_input=True)
        db_ok, db_detail = _database_check(build_dsn(password, candidate))
        if db_ok:
            break
        console.print(f"[red]OpenSQL 로그인 실패 ({attempt}/3): {db_detail}[/red]")
    if not db_ok:
        console.print(
            "[yellow]잘못된 비밀번호는 저장하지 않았습니다. 실제 OpenSQL 계정 "
            "비밀번호를 확인한 뒤 다시 실행하세요.[/yellow]"
        )
        raise typer.Exit(1)

    admin_email = typer.prompt("서비스 관리자 이메일", default="admin@localhost")
    admin_name = typer.prompt("서비스 관리자 이름", default="Administrator")
    console.print("[dim]서비스 로그인용 비밀번호이며 DB 비밀번호와 별개입니다.[/dim]")
    admin_password = _confirmed_password("서비스 관리자 로그인 비밀번호")

    config = save_config(**candidate)
    remembered = False
    if typer.confirm("운영체제 자격 증명 저장소에 DB 비밀번호를 보관할까요?", default=True):
        try:
            save_password(password, config)
            remembered = True
        except Exception as exc:
            console.print(f"[yellow]DB 비밀번호를 저장하지 못했습니다: {exc}[/yellow]")

    table = Table(title="설정 검사", show_header=True)
    table.add_column("항목")
    table.add_column("상태")
    table.add_column("상세")
    table.add_row("설정 파일", "[green]완료[/green]", str(CONFIG_FILE))
    table.add_row("OpenProxy", "[green]정상[/green]", tcp_detail)
    table.add_row("OpenSQL 로그인", "[green]정상[/green]", db_detail)
    table.add_row(
        "DB 비밀번호",
        "[green]안전 저장[/green]" if remembered else "[yellow]실행 시 입력[/yellow]",
        "설정 파일에는 저장되지 않음",
    )
    try:
        from services.api.auth import bootstrap_owner

        access_token, workspace_id = bootstrap_owner(
            admin_email, admin_name, build_dsn(password, config), admin_password
        )
        save_access_token(access_token, api_url)
        table.add_row(
            "관리자 계정", "[green]완료[/green]", f"{admin_email} / workspace {workspace_id[:8]}"
        )
    except Exception as exc:
        table.add_row("관리자 계정", "[red]실패[/red]", str(exc))
        console.print(table)
        raise typer.Exit(1)

    console.print(table)
    console.print(
        "\n다음 명령 하나로 서버를 실행하세요:\n[bold cyan]  tibero-doc serve[/bold cyan]"
    )


def serve_command(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """저장된 설정으로 API 서버를 실행합니다."""

    config = load_config()
    password = os.getenv("TIBERO_DOC_DB_PASSWORD") or load_password(config)
    if not password:
        password = typer.prompt("OpenSQL postgres 비밀번호", hide_input=True)

    db_ok, db_detail = _database_check(build_dsn(password, config))
    if not db_ok:
        console.print("[red]API 서버를 시작하지 않았습니다: OpenSQL 로그인 실패[/red]")
        console.print(f"[dim]{db_detail}[/dim]")
        console.print(
            "저장된 DB 비밀번호가 실제 계정과 다릅니다. "
            "`tibero-doc setup`을 다시 실행해 올바른 값으로 교체하세요."
        )
        raise typer.Exit(1)

    os.environ.update(runtime_environment(password, config))
    console.print(
        Panel.fit(
            f"[bold green]Tibero Doc API 시작[/bold green]\n"
            f"API: http://{host}:{port}\nDocs: http://{host}:{port}/docs\n"
            f"DB: {config['db_host']}:{config['db_port']}/{config['db_name']} ({db_detail})\n"
            f"Embedding: {config['embedding_provider']} / {config['embedding_model']}",
            border_style="green",
        )
    )
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter(
            "API 패키지가 없습니다. pip install -e 'services/api'를 실행하세요."
        ) from exc
    uvicorn.run("services.api.main:app", host=host, port=port, reload=reload)


def doctor_command() -> None:
    """설정, OpenProxy, OpenSQL, API를 한 번에 진단합니다."""

    config = load_config()
    password = os.getenv("TIBERO_DOC_DB_PASSWORD") or load_password(config)
    checks: list[tuple[str, bool, str]] = []
    checks.append(("설정 파일", CONFIG_FILE.exists(), str(CONFIG_FILE)))
    tcp_ok, tcp_detail = _tcp_check(str(config["db_host"]), int(config["db_port"]))
    checks.append(("OpenProxy 포트", tcp_ok, tcp_detail))
    if password and tcp_ok:
        db_ok, db_detail = _database_check(build_dsn(password, config))
    else:
        db_ok, db_detail = False, "저장된 비밀번호 없음" if not password else "포트 연결 실패"
    checks.append(("OpenSQL 로그인", db_ok, db_detail))
    try:
        response = httpx.get(f"{config['api_url'].rstrip('/')}/health", timeout=3)
        api_ok = response.status_code == 200
        api_detail = "healthy" if api_ok else response.text[:160]
    except httpx.HTTPError as exc:
        api_ok, api_detail = False, str(exc)
    checks.append(("API 서버", api_ok, api_detail))

    table = Table(title="Tibero Doc Doctor")
    table.add_column("검사")
    table.add_column("결과")
    table.add_column("상세")
    for name, ok, detail in checks:
        table.add_row(name, "[green]✓ 정상[/green]" if ok else "[red]✗ 확인 필요[/red]", detail)
    console.print(table)
    if not CONFIG_FILE.exists():
        console.print("[cyan]해결: tibero-doc setup[/cyan]")
    elif not db_ok:
        console.print("[cyan]해결: tibero-doc setup (실제 OpenSQL 비밀번호 입력)[/cyan]")
    elif not api_ok:
        console.print("[cyan]해결: tibero-doc serve[/cyan]")
    if not all(ok for _, ok, _ in checks):
        raise typer.Exit(1)
