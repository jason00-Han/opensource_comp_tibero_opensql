import typer

from tibero_doc.commands.init import init_command
from tibero_doc.commands.ingest import ingest_command
from tibero_doc.commands.search import search_command
from tibero_doc.commands.status import status_command
from tibero_doc.commands.sync import sync_command

app = typer.Typer(
    name="tibero-doc",
    help="OpenSQL 기반 AI 문서 데이터 플랫폼 CLI",
    no_args_is_help=True,
)

app.command("init")(init_command)
app.command("ingest")(ingest_command)
app.command("search")(search_command)
app.command("sync")(sync_command)
app.command("status")(status_command)

@app.callback()
def main():
    """
    Tibero Doc CLI

    문서 업로드 → 임베딩 → 검색 → 동기화 → MCP를
    OpenSQL 기반에서 관리합니다.
    """
    pass


if __name__ == "__main__":
    app()