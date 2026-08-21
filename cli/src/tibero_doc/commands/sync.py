import typer
import httpx

from rich.console import Console

from tibero_doc.client import TiberoDocClient


console = Console()


def sync_command():

    client = TiberoDocClient()

    console.print(
        "[cyan]Synchronizing documents...[/cyan]"
    )

    try:

        result = client.sync()

    except httpx.HTTPError as e:

        console.print(
            f"[red]Sync failed: {e}[/red]"
        )

        raise typer.Exit(1)

    console.print(
        "[green]Synchronization requested[/green]"
    )

    result = result.get("result") or result

    console.print(
        f"Added   : {result.get('added', 0)}"
    )

    console.print(
        f"Updated : {result.get('updated', 0)}"
    )

    console.print(
        f"Deleted : {result.get('deleted', 0)}"
    )

    console.print(
        f"Skipped : {result.get('skipped', 0)}"
    )
