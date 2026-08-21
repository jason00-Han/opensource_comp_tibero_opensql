import typer
from rich.console import Console
from rich.table import Table

from tibero_doc.client import TiberoDocClient


console = Console()


def ask_command(question: str = typer.Argument(...), top_k: int = typer.Option(5, "--top-k", "-k")) -> None:
    """관련 문서를 찾아 근거와 함께 질문에 답합니다."""
    data = TiberoDocClient().ask(question, top_k)
    console.print(f"\n[bold cyan]답변[/bold cyan]\n{data['answer']}\n")
    table = Table(title=f"근거 문서 · {data['provider']}")
    for column in ("#", "문서", "청크", "점수"):
        table.add_column(column)
    for item in data.get("citations", []):
        table.add_row(str(item["index"]), item["filename"], str(item["chunk_index"]), str(item.get("score", "-")))
    console.print(table)
