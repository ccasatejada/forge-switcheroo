import re

from typer.testing import CliRunner

from forge_switcheroo import __version__
from forge_switcheroo.cli import app

runner = CliRunner()
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def plain_output(output: str) -> str:
    """Remove terminal styling before asserting on human-readable CLI help."""
    return ANSI_ESCAPE.sub("", output)


def test_help_lists_commands_and_global_options() -> None:
    result = runner.invoke(app, ["--help"])
    output = plain_output(result.stdout)

    assert result.exit_code == 0
    assert "Convert and migrate a repository" in output
    assert "auth-check" in output
    assert "inspect" in output
    assert "migrate" in output
    assert "--version" in output


def test_migrate_help_describes_optional_remote_publishing() -> None:
    result = runner.invoke(app, ["migrate", "--help"])
    output = plain_output(result.stdout)

    assert result.exit_code == 0
    assert "--publish" in output
    assert "--repository" in output
    assert "--visibility" in output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert plain_output(result.stdout).strip() == f"forge-switcheroo {__version__}"
