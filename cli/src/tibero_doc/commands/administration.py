from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

from tibero_doc.client import TiberoDocClient
from tibero_doc.config import get_api_url, load_access_token, load_config, load_password, runtime_environment, save_access_token


console = Console()
group_app = typer.Typer(help="그룹과 그룹 멤버를 관리합니다.")
acl_app = typer.Typer(help="문서별 사용자·그룹 권한을 관리합니다.")
workspace_app = typer.Typer(help="워크스페이스를 조회하고 전환합니다.")
user_app = typer.Typer(help="워크스페이스 사용자를 관리합니다.")
mcp_app = typer.Typer(help="MCP 서버를 실행하고 상태를 확인합니다.")
worker_app = typer.Typer(help="RabbitMQ Worker 상태를 확인합니다.")
storage_app = typer.Typer(help="원본 저장소와 Redis 캐시를 점검합니다.")
deploy_app = typer.Typer(help="운영 배포 구성을 점검합니다.")
failover_app = typer.Typer(help="OpenSQL HA Failover를 시연합니다.")
retention_app = typer.Typer(help="오래된 비정형 문서의 보존 후보를 분석합니다.")


def _table(title, columns, rows):
    table = Table(title=title)
    for column in columns: table.add_column(column)
    for row in rows: table.add_row(*(str(value) for value in row))
    console.print(table)


@group_app.command("create")
def group_create(name: str):
    data = TiberoDocClient().create_group(name); console.print(f"[green]그룹 생성 완료[/green] {data['group_id']} {data['name']}")


@group_app.command("list")
def group_list():
    rows = TiberoDocClient().groups()["groups"]
    _table("Groups", ("ID", "Name", "Members"), ((r["group_id"], r["name"], r["member_count"]) for r in rows))


@group_app.command("add-member")
def group_add_member(group_id: str, user_id: str):
    TiberoDocClient().add_group_member(group_id, user_id); console.print("[green]멤버를 추가했습니다.[/green]")


@group_app.command("remove-member")
def group_remove_member(group_id: str, user_id: str):
    TiberoDocClient().remove_group_member(group_id, user_id); console.print("[green]멤버를 제거했습니다.[/green]")


@acl_app.command("grant")
def acl_grant(document_id: str, principal_id: str, principal_type: str = typer.Option("user", "--type"), permission: str = typer.Option("read", "--permission", "-p")):
    TiberoDocClient().grant_acl(document_id, principal_type, principal_id, permission); console.print("[green]권한을 부여했습니다.[/green]")


@acl_app.command("revoke")
def acl_revoke(document_id: str, principal_id: str, principal_type: str = typer.Option("user", "--type")):
    TiberoDocClient().revoke_acl(document_id, principal_type, principal_id); console.print("[green]권한을 회수했습니다.[/green]")


@acl_app.command("list")
def acl_list(document_id: str):
    rows = TiberoDocClient().acl(document_id)["acl"]
    _table("Document ACL", ("Type", "Principal", "Permission", "Granted"), ((r["principal_type"], r["principal_id"], r["permission"], r["created_at"]) for r in rows))


@workspace_app.command("list")
def workspace_list():
    rows = TiberoDocClient().workspaces()["workspaces"]
    _table("Workspaces", ("Current", "ID", "Organization", "Name", "Role"), (("*" if r["current"] else "", r["workspace_id"], r["organization"], r["name"], r["role"]) for r in rows))


@workspace_app.command("use")
def workspace_use(workspace_id: str):
    client = TiberoDocClient(); data = client.switch_workspace(workspace_id); save_access_token(data["access_token"], client.api_url); console.print(f"[green]워크스페이스 전환 완료[/green] {workspace_id}")


@user_app.command("list")
def user_list():
    rows = TiberoDocClient().users()["users"]
    _table("Users", ("ID", "Email", "Name", "Role", "Status"), ((r["user_id"], r["email"], r["display_name"], r["role"], r["status"]) for r in rows))


@user_app.command("change-role")
def user_change_role(user_id: str, role: str):
    TiberoDocClient().change_role(user_id, role); console.print(f"[green]역할 변경 완료[/green] {role}")


@user_app.command("disable")
def user_disable(user_id: str, yes: bool = typer.Option(False, "--yes", "-y")):
    if not yes and not typer.confirm(f"사용자 {user_id}를 비활성화할까요?"): raise typer.Abort()
    TiberoDocClient().disable_user(user_id); console.print("[green]사용자를 비활성화했습니다.[/green]")


def download_command(document_id: str, output: Path | None = typer.Option(None, "--output", "-o")):
    response = TiberoDocClient().download(document_id)
    filename = output or Path(response.headers.get("content-disposition", "").split("filename=")[-1].strip('"') or document_id)
    filename.write_bytes(response.content); console.print(f"[green]다운로드 완료[/green] {filename.resolve()}")


@mcp_app.command("serve")
def mcp_serve(transport: str = typer.Option("stdio", "--transport"), host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8001)):
    config = load_config(); password = load_password(config)
    if not password: raise typer.BadParameter("저장된 DB 비밀번호가 없습니다. tibero-doc setup을 먼저 실행하세요.")
    env = dict(os.environ); env.update(runtime_environment(password, config)); env.update(MCP_TRANSPORT=transport, MCP_HOST=host, MCP_PORT=str(port), TIBERO_DOC_ACCESS_TOKEN=load_access_token() or "")
    raise typer.Exit(subprocess.call([sys.executable, "-m", "services.mcp_server.main"], env=env))


@mcp_app.command("status")
def mcp_status(url: str = typer.Option("http://127.0.0.1:8001/mcp")):
    try:
        response = httpx.get(url, timeout=3); console.print(f"[green]MCP 응답[/green] HTTP {response.status_code}")
    except httpx.HTTPError as exc:
        console.print(f"[red]MCP 연결 실패[/red] {exc}"); raise typer.Exit(1)


@worker_app.command("status")
def worker_status():
    try:
        import pika
        connection = pika.BlockingConnection(pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")))
        channel = connection.channel(); rows = []
        for queue in ("tibero_doc.ingest", "tibero_doc.embedding", "tibero_doc.sync"):
            result = channel.queue_declare(queue=queue, passive=True); rows.append((queue, result.method.message_count, result.method.consumer_count))
        connection.close(); _table("Workers", ("Queue", "Messages", "Consumers"), rows)
    except Exception as exc:
        console.print(f"[red]RabbitMQ 점검 실패[/red] {exc}"); raise typer.Exit(1)


@storage_app.command("status")
def storage_status():
    console.print_json(json.dumps(TiberoDocClient().storage_status(), ensure_ascii=False, default=str))


@retention_app.command("plan")
def retention_plan(hot_days: int = typer.Option(30), cold_days: int = typer.Option(180), delete_days: int = typer.Option(365)):
    data = TiberoDocClient().retention_plan(hot_days, cold_days, delete_days)
    rows = []
    for bucket, documents in data["buckets"].items():
        for document in documents: rows.append((bucket, document["document_id"], document["filename"], document["age_days"]))
    _table("Retention plan (dry-run)", ("Tier", "ID", "Filename", "Age days"), rows)
    console.print("[yellow]자동 삭제는 비활성화되어 있습니다. 이 명령은 후보만 표시합니다.[/yellow]")


@deploy_app.command("check")
def deploy_check():
    root = Path(__file__).resolve().parents[4]
    checks = [("API", False, get_api_url()), ("Nginx config", (root / "infra/nginx/tibero-doc.conf").is_file(), "infra/nginx/tibero-doc.conf"), ("Production compose", (root / "infra/docker-compose.production.yml").is_file(), "infra/docker-compose.production.yml"), ("HA compose", (root / "infra/docker-compose.ha.yml").is_file(), "infra/docker-compose.ha.yml")]
    try: checks[0] = ("API", httpx.get(get_api_url().rstrip("/") + "/health/ready", timeout=3).status_code == 200, get_api_url())
    except httpx.HTTPError: pass
    _table("Deployment check", ("Item", "Status", "Detail"), ((n, "OK" if ok else "FAIL", d) for n, ok, d in checks))
    if not all(ok for _, ok, _ in checks): raise typer.Exit(1)


@failover_app.command("demo")
def failover_demo(yes: bool = typer.Option(False, "--yes", "-y")):
    if not yes and not typer.confirm("현재 HA Primary를 중지하고 자동 전환을 시연할까요?"): raise typer.Abort()
    script = Path(__file__).resolve().parents[4] / "infra/scripts/failover-demo.ps1"
    raise typer.Exit(subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]))
