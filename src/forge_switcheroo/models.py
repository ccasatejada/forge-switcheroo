from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Forge(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"

    @property
    def opposite(self) -> Forge:
        return Forge.GITLAB if self is Forge.GITHUB else Forge.GITHUB


class Feature(StrEnum):
    CI = "ci"
    TEMPLATES = "templates"


@dataclass(frozen=True, slots=True)
class ProjectInspection:
    path: Path
    forge: Forge
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MigrationRequest:
    source: Path
    destination: Path
    source_forge: Forge
    target_forge: Forge
    features: frozenset[Feature]


@dataclass(frozen=True, slots=True)
class MigrationResult:
    destination: Path
    actions: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    forge: Forge
    hostname: str
    username: str
