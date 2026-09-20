from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from forge_switcheroo.converters import convert_templates, generate_ci
from forge_switcheroo.models import Feature, Forge, MigrationRequest, MigrationResult


class MigrationError(RuntimeError):
    """Raised when a migration cannot be performed safely."""


def validate_request(request: MigrationRequest) -> None:
    if request.source_forge is request.target_forge:
        raise MigrationError("Source and target forges must be different.")
    if request.destination.exists():
        raise MigrationError(f"Destination already exists: {request.destination}")
    try:
        request.destination.resolve().relative_to(request.source.resolve())
    except ValueError:
        pass
    else:
        raise MigrationError("Destination cannot be located inside the source repository.")
    if not request.destination.parent.is_dir():
        raise MigrationError(f"Destination parent does not exist: {request.destination.parent}")
    if not (request.source / ".git").is_dir():
        raise MigrationError(
            "Repositories where .git is not a directory (including linked worktrees) "
            "are not supported yet."
        )

    _compute_converted_paths(request)


def _compute_converted_paths(request):
    generated_paths: list[Path] = []
    if Feature.CI in request.features:
        generated_paths.append(
            Path(".gitlab-ci.yml")
            if request.target_forge is Forge.GITLAB
            else Path(".github/workflows/ci.yml")
        )
    if Feature.TEMPLATES in request.features:
        generated_paths.append(
            Path(".gitlab/issue_templates")
            if request.target_forge is Forge.GITLAB
            else Path(".github/ISSUE_TEMPLATE")
        )
    for relative in generated_paths:
        current = request.source
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise MigrationError(
                    f"Conversion refused: target path {relative} traverses a symbolic link."
                )


def _rename_origin(project: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project), "remote"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or "origin" not in completed.stdout.splitlines():
        return "No origin remote to neutralize"
    renamed = subprocess.run(
        ["git", "-C", str(project), "remote", "rename", "origin", "source"],
        check=False,
        capture_output=True,
        text=True,
    )
    if renamed.returncode != 0:
        raise MigrationError(f"Could not rename the origin remote: {renamed.stderr.strip()}")
    return "Renamed origin remote to source"


def migrate(
    request: MigrationRequest, progress: Callable[[str], None] | None = None
) -> MigrationResult:
    validate_request(request)
    notify = progress or (lambda _message: None)
    temporary = request.destination.parent / f".{request.destination.name}.switcheroo-{uuid4().hex}"
    actions: list[str] = []
    warnings: list[str] = []
    try:
        notify("Copying the repository and its Git history…")
        shutil.copytree(request.source, temporary, symlinks=True)
        actions.append("Copied repository and Git history")
        notify("Neutralizing the original remote…")
        actions.append(_rename_origin(temporary))

        if Feature.CI in request.features:
            notify("Preparing the target CI configuration…")
            action, warning = generate_ci(temporary, request.target_forge)
            actions.append(action)
            if warning:
                warnings.append(warning)
        if Feature.TEMPLATES in request.features:
            notify("Adapting issue templates…")
            actions.extend(convert_templates(temporary, request.source_forge, request.target_forge))

        notify("Writing the migration report…")
        report = {
            "source": str(request.source),
            "destination": str(request.destination),
            "source_forge": request.source_forge.value,
            "target_forge": request.target_forge.value,
            "features": sorted(feature.value for feature in request.features),
            "actions": actions,
            "warnings": warnings,
        }
        (temporary / ".forge-switcheroo-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, request.destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return MigrationResult(request.destination, tuple(actions), tuple(warnings))
