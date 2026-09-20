from typer.testing import CliRunner

from forge_switcheroo import __version__
from forge_switcheroo.cli import app

runner = CliRunner()


def test_help_lists_commands_and_global_options() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Migrate a local repository copy" in result.stdout
    assert "auth-check" in result.stdout
    assert "inspect" in result.stdout
    assert "migrate" in result.stdout
    assert "--version" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"forge-switcheroo {__version__}"
