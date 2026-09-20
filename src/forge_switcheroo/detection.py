from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any

from forge_switcheroo.models import Forge, ProjectInspection


class DetectionError(ValueError):
    """Raised when a directory is not a repository or its forge is ambiguous."""


def _remote_urls(git_config: Path) -> list[str]:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(git_config, encoding="utf-8")
    except configparser.Error:
        return []
    return [
        parser.get(section, "url")
        for section in parser.sections()
        if section.startswith('remote "') and parser.has_option(section, "url")
    ]


def inspect_project(path: Path) -> ProjectInspection:
    project = path.expanduser().resolve()
    if not project.is_dir():
        raise DetectionError(f"Directory does not exist: {project}")
    if not (project / ".git").exists():
        raise DetectionError(f"Directory is not a Git repository: {project}")

    signals = _gather_forge_context(project)

    detected = [forge for forge, evidence in signals.items() if evidence]
    if not detected:
        raise DetectionError(
            "Could not determine the forge: no GitHub/GitLab remote or forge-specific files found."
        )
    if len(detected) > 1:
        remote_detected = [
            forge
            for forge in detected
            if any(item.startswith("remote ") for item in signals[forge])
        ]
        if len(remote_detected) != 1:
            raise DetectionError("Ambiguous forge: both GitHub and GitLab markers are present.")
        detected = remote_detected

    forge = detected[0]
    return ProjectInspection(project, forge, tuple(signals[forge]))


def _gather_forge_context(project: Path) -> dict[Any, list[str]]:
    signals: dict[Forge, list[str]] = {Forge.GITHUB: [], Forge.GITLAB: []}
    if (project / ".github").is_dir():
        signals[Forge.GITHUB].append(".github directory")
    if (project / ".gitlab-ci.yml").is_file() or (project / ".gitlab").is_dir():
        signals[Forge.GITLAB].append("GitLab configuration")

    git_config = project / ".git" / "config"
    if git_config.is_file():
        for url in _remote_urls(git_config):
            lowered = url.lower()
            if "github.com" in lowered:
                signals[Forge.GITHUB].append(f"remote {url}")
            if "gitlab" in lowered:
                signals[Forge.GITLAB].append(f"remote {url}")
    return signals
