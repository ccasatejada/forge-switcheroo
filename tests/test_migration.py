import json
import subprocess
from pathlib import Path

import pytest

from forge_switcheroo.migration import MigrationError, migrate
from forge_switcheroo.models import Feature, Forge, MigrationRequest


def make_repository(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "git@github.com:acme/demo.git"],
        check=True,
    )
    (path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    templates = path / ".github" / "ISSUE_TEMPLATE"
    templates.mkdir(parents=True)
    (templates / "bug.md").write_text("# Bug\n", encoding="utf-8")


def test_migration_copies_and_converts_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "converted"
    make_repository(source)
    request = MigrationRequest(
        source,
        destination,
        Forge.GITHUB,
        Forge.GITLAB,
        frozenset({Feature.CI, Feature.TEMPLATES}),
    )

    result = migrate(request)

    assert result.destination == destination
    assert not (source / ".gitlab-ci.yml").exists()
    assert (destination / ".gitlab-ci.yml").is_file()
    assert (destination / ".gitlab" / "issue_templates" / "bug.md").is_file()
    report = json.loads((destination / ".forge-switcheroo-report.json").read_text())
    assert report["source_forge"] == "github"
    remotes = subprocess.run(
        ["git", "-C", str(destination), "remote"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert remotes == ["source"]


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "converted"
    make_repository(source)
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("safe", encoding="utf-8")
    request = MigrationRequest(source, destination, Forge.GITHUB, Forge.GITLAB, frozenset())

    with pytest.raises(MigrationError, match="already exists"):
        migrate(request)
    assert marker.read_text(encoding="utf-8") == "safe"


def test_conversion_rejects_target_below_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    external = tmp_path / "external"
    destination = tmp_path / "converted"
    make_repository(source)
    external.mkdir()
    (source / ".github").rename(source / ".github-original")
    (source / ".github").symlink_to(external, target_is_directory=True)
    request = MigrationRequest(
        source, destination, Forge.GITLAB, Forge.GITHUB, frozenset({Feature.CI})
    )

    with pytest.raises(MigrationError, match="symbolic link"):
        migrate(request)
    assert not destination.exists()
    assert list(external.iterdir()) == []


def test_linked_worktree_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / ".git").write_text("gitdir: /somewhere/else\n", encoding="utf-8")
    request = MigrationRequest(
        source, tmp_path / "converted", Forge.GITHUB, Forge.GITLAB, frozenset()
    )

    with pytest.raises(MigrationError, match="worktrees"):
        migrate(request)


def test_migration_converts_main_instead_of_current_feature_branch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "converted"
    source.mkdir()
    subprocess.run(["git", "init", "-q", "--initial-branch=main", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Test User"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True
    )
    (source / ".github").mkdir()
    (source / "README.md").write_text("main\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-q", "-m", "Initial"], check=True)
    subprocess.run(["git", "-C", str(source), "checkout", "-q", "-b", "feature"], check=True)
    (source / "README.md").write_text("feature\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "commit", "-q", "-am", "Feature"], check=True)
    request = MigrationRequest(
        source, destination, Forge.GITHUB, Forge.GITLAB, frozenset({Feature.CI})
    )

    result = migrate(request)

    assert result.branch == "main"
    assert (destination / "README.md").read_text(encoding="utf-8") == "main\n"
