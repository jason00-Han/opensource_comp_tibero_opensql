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


def _http_error_detail(error: httpx.HTTPError) -> str:
    """API가 제공한 오류 메시지를 CLI 사용자가 바로 조치할 수 있게 표시한다."""
    if isinstance(error, httpx.HTTPStatusError):
        try:
            payload = error.response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if isinstance(detail, list):
                return "; ".join(
                    str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                    for item in detail
                )
            if detail:
                return str(detail)
        except (ValueError, TypeError):
            pass
    if isinstance(error, httpx.TimeoutException):
        return (
            "업로드 시간이 초과되었습니다. API가 queue 모드로 재시작되었는지, "
            "RabbitMQ/저장소가 정상인지 확인하세요. 큰 파일은 "
            "TIBERO_DOC_HTTP_TIMEOUT_SECONDS 값을 더 크게 설정하거나 0으로 설정해 제한을 해제할 수 있습니다."
        )
    return str(error)


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
                "[green]✓[/green] ", file.name,
            )

            success += 1

        except httpx.HTTPError as e:

            console.print(
                "[red]✗[/red] ", file.name, " - ", _http_error_detail(e),
            )

    console.print()

    console.print(
        f"[green]{success}[/green]"
        f"/{len(files)} documents uploaded"
    )
