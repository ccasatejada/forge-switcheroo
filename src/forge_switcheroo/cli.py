from __future__ import annotations

from pathlib import Path
from typing import Annotated

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forge_switcheroo import __version__
from forge_switcheroo.auth import AuthenticationError, check_authentication, default_hostname
from forge_switcheroo.detection import DetectionError, inspect_project
from forge_switcheroo.migration import MigrationError, migrate, validate_request
from forge_switcheroo.models import Feature, Forge, MigrationRequest, MigrationResult

app = typer.Typer(
    add_completion=True,
    no_args_is_help=False,
    help="Migrate a local repository copy between GitHub and GitLab.",
)
console = Console()


def _abort_if_none(value: str | list[str] | None) -> str | list[str]:
    if value is None:
        raise typer.Abort()
    return value


def _display_plan(request: MigrationRequest) -> None:
    table = Table(title="Migration plan", show_header=False)
    table.add_row("Source", str(request.source))
    table.add_row("Forge", f"{request.source_forge.value} → {request.target_forge.value}")
    table.add_row("Destination", str(request.destination))
    table.add_row("Options", ", ".join(sorted(item.value for item in request.features)) or "none")
    console.print(table)


def _display_result(result: MigrationResult) -> None:
    lines = [f"[green]✓[/green] {action}" for action in result.actions]
    lines.extend(f"[yellow]![/yellow] {warning}" for warning in result.warnings)
    console.print(
        Panel("\n".join(lines), title="Migration complete", subtitle=str(result.destination))
    )


def _run(request: MigrationRequest, *, assume_yes: bool) -> None:
    try:
        validate_request(request)
    except MigrationError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error
    _display_plan(request)
    if not assume_yes and not questionary.confirm("Start this migration?", default=False).ask():
        raise typer.Abort()
    try:
        result = migrate(
            request, progress=lambda message: console.print(f"[cyan]→[/cyan] {message}")
        )
    except MigrationError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error
    _display_result(result)


def _check_and_display_authentication(forge: Forge, hostname: str) -> None:
    try:
        user = check_authentication(forge, hostname)
    except AuthenticationError as error:
        console.print(f"[red]Authentication error:[/red] {error}")
        raise typer.Exit(1) from error
    console.print(
        f"[green]✓[/green] Authenticated to {user.hostname} as [bold]{user.username}[/bold]"
    )


def wizard() -> None:
    console.print(Panel("Local GitHub ↔ GitLab migration", style="bold cyan"))
    source_answer = _abort_if_none(
        questionary.path(
            "Project directory to migrate:",
            default=str(Path.cwd()),
            only_directories=True,
        ).ask()
    )
    source = Path(str(source_answer)).expanduser().resolve()
    try:
        inspection = inspect_project(source)
    except DetectionError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error
    console.print(
        f"Detected forge: [bold]{inspection.forge.value}[/bold] "
        f"([dim]{', '.join(inspection.evidence)}[/dim])"
    )

    target_answer = _abort_if_none(
        questionary.select(
            "Target forge:",
            choices=[
                questionary.Choice(
                    forge.value,
                    forge.value,
                    disabled="source forge" if forge is inspection.forge else None,
                )
                for forge in Forge
            ],
            default=inspection.forge.opposite.value,
        ).ask()
    )
    target_forge = Forge(str(target_answer))
    target_host_answer = _abort_if_none(
        questionary.text(
            "Target forge hostname:",
            default=default_hostname(target_forge),
            validate=lambda value: bool(value.strip()),
        ).ask()
    )
    if questionary.confirm("Check target API authentication now?", default=True).ask():
        _check_and_display_authentication(target_forge, str(target_host_answer))
    name_answer = _abort_if_none(
        questionary.text(
            "New project name:",
            default=f"{source.name}-{target_answer}",
            validate=lambda value: bool(value.strip()) and Path(value).name == value,
        ).ask()
    )
    parent_answer = _abort_if_none(
        questionary.path(
            "Destination parent directory:",
            default=str(source.parent),
            only_directories=True,
        ).ask()
    )
    features_answer = _abort_if_none(
        questionary.checkbox(
            "Components to adapt:",
            choices=[
                questionary.Choice(
                    "CI pipeline (conservative generation)", Feature.CI.value, checked=True
                ),
                questionary.Choice("Issue templates", Feature.TEMPLATES.value, checked=True),
            ],
        ).ask()
    )
    request = MigrationRequest(
        source=source,
        destination=Path(str(parent_answer)).expanduser().resolve() / str(name_answer),
        source_forge=inspection.forge,
        target_forge=target_forge,
        features=frozenset(Feature(value) for value in features_answer),
    )
    _run(request, assume_yes=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Open the interactive wizard when no subcommand is provided."""
    if version:
        console.print(f"forge-switcheroo {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        wizard()


@app.command("inspect")
def inspect_command(
    project: Annotated[Path, typer.Argument(exists=True, file_okay=False, resolve_path=True)],
) -> None:
    """Detect the forge associated with a local repository."""
    try:
        inspection = inspect_project(project)
    except DetectionError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error
    console.print(f"[bold]{inspection.forge.value}[/bold] — {', '.join(inspection.evidence)}")


@app.command("auth-check")
def auth_check_command(
    forge: Annotated[Forge, typer.Argument(help="Forge whose API access should be checked.")],
    hostname: Annotated[
        str | None,
        typer.Option("--hostname", "-H", help="Forge hostname, without a scheme or path."),
    ] = None,
) -> None:
    """Check API authentication through the official forge CLI."""
    _check_and_display_authentication(forge, hostname or default_hostname(forge))


@app.command("migrate")
def migrate_command(
    source: Annotated[Path, typer.Argument(exists=True, file_okay=False, resolve_path=True)],
    destination: Annotated[Path, typer.Argument(resolve_path=True)],
    target: Annotated[Forge, typer.Option("--target", "-t")],
    features: Annotated[list[Feature] | None, typer.Option("--feature", "-f")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Run a local migration; suitable for scripts."""
    try:
        inspection = inspect_project(source)
    except DetectionError as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(1) from error
    request = MigrationRequest(
        source=source,
        destination=destination,
        source_forge=inspection.forge,
        target_forge=target,
        features=frozenset(features or []),
    )
    _run(request, assume_yes=yes)
