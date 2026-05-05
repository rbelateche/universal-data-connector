"""UDC CLI — entry point (Phase 5 will fill this out)."""

import typer
from rich.console import Console

app = typer.Typer(
    name="udc",
    help="Universal Data Connector — map any data source to a canonical schema.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the current UDC version."""
    from udc import __version__

    console.print(f"udc v{__version__}")


if __name__ == "__main__":
    app()
