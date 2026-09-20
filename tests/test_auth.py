import subprocess

import pytest

from forge_switcheroo.auth import AuthenticationError, check_authentication
from forge_switcheroo.models import Forge


def test_github_authentication_uses_cli_without_requesting_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    monkeypatch.setattr(
        "forge_switcheroo.auth.shutil.which", lambda executable: f"/bin/{executable}"
    )

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        output = '{"login":"octocat"}' if command[1] == "api" else ""
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("forge_switcheroo.auth._run", fake_run)

    user = check_authentication(Forge.GITHUB, "github.com")

    assert user.username == "octocat"
    assert commands == [
        ["gh", "auth", "status", "--active", "--hostname", "github.com"],
        ["gh", "api", "user", "--hostname", "github.com"],
    ]
    assert all("token" not in argument for command in commands for argument in command)


def test_gitlab_authentication_supports_private_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("forge_switcheroo.auth.shutil.which", lambda _executable: "/bin/glab")

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        output = '{"username":"alice"}' if command[1] == "api" else ""
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("forge_switcheroo.auth._run", fake_run)

    user = check_authentication(Forge.GITLAB, "gitlab.corp.example")

    assert user.hostname == "gitlab.corp.example"
    assert user.username == "alice"


def test_missing_forge_cli_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("forge_switcheroo.auth.shutil.which", lambda _executable: None)

    with pytest.raises(AuthenticationError, match="not installed"):
        check_authentication(Forge.GITLAB, "gitlab.com")


def test_invalid_hostname_is_rejected_before_running_a_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("forge_switcheroo.auth.shutil.which", lambda _executable: "/bin/gh")

    with pytest.raises(AuthenticationError, match="scheme"):
        check_authentication(Forge.GITHUB, "https://github.com/acme")
