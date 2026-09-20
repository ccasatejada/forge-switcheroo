from pathlib import Path

import pytest

from forge_switcheroo.detection import DetectionError, inspect_project
from forge_switcheroo.models import Forge


def make_git_config(project: Path, url: str) -> None:
    git_dir = project / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text(f'[remote "origin"]\n\turl = {url}\n', encoding="utf-8")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:acme/demo.git", Forge.GITHUB),
        ("https://gitlab.com/acme/demo.git", Forge.GITLAB),
        ("ssh://git@gitlab.acme.test/acme/demo.git", Forge.GITLAB),
    ],
)
def test_detects_forge_from_remote(tmp_path: Path, url: str, expected: Forge) -> None:
    make_git_config(tmp_path, url)
    assert inspect_project(tmp_path).forge is expected


def test_rejects_unknown_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    with pytest.raises(DetectionError, match="Could not determine"):
        inspect_project(tmp_path)
