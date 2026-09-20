import json
import subprocess
from pathlib import Path

import pytest

from forge_switcheroo.models import AuthenticatedUser, Forge, PublishRequest, Visibility
from forge_switcheroo.publish import (
    PublishError,
    ensure_clean_repository,
    publish_repository,
    validate_publish_request,
)


def run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def make_committed_repository(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q", "--initial-branch=main", str(path)], check=True)
    run_git(path, "config", "user.name", "Test User")
    run_git(path, "config", "user.email", "test@example.com")
    (path / "README.md").write_text("# Original\n", encoding="utf-8")
    run_git(path, "add", "README.md")
    run_git(path, "commit", "-q", "-m", "Initial commit")


def test_publish_commits_conversion_and_pushes_only_primary_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "converted"
    remote = tmp_path / "remote.git"
    make_committed_repository(repository)
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    (repository / ".gitlab-ci.yml").write_text("test:\n  script: echo ok\n", encoding="utf-8")
    report_path = repository / ".forge-switcheroo-report.json"
    report_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        "forge_switcheroo.publish._create_remote",
        lambda _request, _user: (str(remote), "https://gitlab.example/acme/demo"),
    )
    request = PublishRequest(Forge.GITLAB, "gitlab.example", "acme/demo", Visibility.PRIVATE)
    user = AuthenticatedUser(Forge.GITLAB, "gitlab.example", "alice")

    result = publish_repository(repository, "main", request, user)

    assert result.branch == "main"
    assert run_git(repository, "remote", "get-url", "origin").stdout.strip() == str(remote)
    branches = subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert branches == ["main"]
    report = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "main:.forge-switcheroo-report.json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert report.returncode != 0
    local_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert local_report["publication"]["web_url"] == "https://gitlab.example/acme/demo"


def test_remote_publish_requires_clean_source(tmp_path: Path) -> None:
    repository = tmp_path / "source"
    make_committed_repository(repository)
    (repository / "uncommitted.txt").write_text("draft", encoding="utf-8")

    with pytest.raises(PublishError, match="clean source"):
        ensure_clean_repository(repository)


def test_repository_names_are_validated() -> None:
    request = PublishRequest(Forge.GITHUB, "github.com", "nested/acme/demo", Visibility.PRIVATE)

    with pytest.raises(PublishError, match="OWNER/NAME"):
        validate_publish_request(request)
