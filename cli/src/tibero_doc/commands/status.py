import httpx

from rich.console import Console
from rich.table import Table

from tibero_doc.client import TiberoDocClient


console = Console()


def status_command():

    client = TiberoDocClient()

    console.print(
        "\n[bold blue]Tibero Doc Platform[/bold blue]\n"
    )

    try:
        data = client.health()

    except httpx.ConnectError:

        console.print(
            "[red]✗ API Server unavailable[/red]"
        )

        raise SystemExit(1)

    except httpx.HTTPError as e:

        console.print(
            f"[red]✗ Health check failed: {e}[/red]"
        )

        raise SystemExit(1)

    table = Table(
        title="Platform Status"
    )

    table.add_column("Component")
    table.add_column("Status")

    components = data.get(
        "components",
        {}
    )

    for name, status in components.items():

        color = (
            "green"
            if status == "healthy"
            else "red"
        )

        table.add_row(
            name,
            f"[{color}]{status}[/{color}]",
        )

    console.print(table)