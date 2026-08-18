import typer

from tibero_doc.commands.ingest import ingest_command
from tibero_doc.commands.collaboration import audit_command, invite_command, join_command, login_command, refresh_command, whoami_command
from tibero_doc.commands.init import init_command
from tibero_doc.commands.manage import delete_command, job_command, list_command, show_command, versions_command
from tibero_doc.commands.onboarding import doctor_command, serve_command, setup_command
from tibero_doc.commands.search import search_command
from tibero_doc.commands.settings import settings_app
from tibero_doc.commands.status import status_command
from tibero_doc.commands.sync import sync_command


app = typer.Typer(
    name="tibero-doc",
    help="OpenSQL 기반 AI 문서 플랫폼 CLI",
    no_args_is_help=True,
)

app.command("setup")(setup_command)
app.command("serve")(serve_command)
app.command("doctor")(doctor_command)
app.command("join")(join_command)
app.command("invite")(invite_command)
app.command("whoami")(whoami_command)
app.command("login")(login_command)
app.command("refresh")(refresh_command)
app.command("audit")(audit_command)
app.command("init", hidden=True)(init_command)
app.command("status")(status_command)
app.command("ingest")(ingest_command)
app.command("search")(search_command)
app.command("sync")(sync_command)
app.command("list")(list_command)
app.command("show")(show_command)
app.command("delete")(delete_command)
app.command("versions")(versions_command)
app.command("job")(job_command)
app.add_typer(settings_app, name="config")


@app.callback()
def main() -> None:
    """문서 업로드, 임베딩, 검색, 동기화와 MCP를 OpenSQL 위에서 관리합니다."""


if __name__ == "__main__":
    app()
