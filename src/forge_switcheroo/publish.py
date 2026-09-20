from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

from forge_switcheroo.models import (
    AuthenticatedUser,
    Forge,
    PublishRequest,
    PublishResult,
)


class PublishError(RuntimeError):
    """Raised when a converted repository cannot be created or pushed."""


def validate_publish_request(request: PublishRequest) -> tuple[str, str]:
    parts = request.repository.strip("/").rsplit("/", 1)
    if len(parts) != 2 or not all(parts):
        raise PublishError("Target repository must use the NAMESPACE/NAME format.")
    namespace, name = parts
    if request.forge is Forge.GITHUB and "/" in namespace:
        raise PublishError("GitHub repositories must use the OWNER/NAME format.")
    return namespace, name


def ensure_clean_repository(repository: Path) -> None:
    result = _git(repository, "status", "--porcelain")
    if result.returncode != 0:
        raise PublishError(f"Could not inspect the source repository: {result.stderr.strip()}")
    if result.stdout.strip():
        raise PublishError(
            "Remote publishing requires a clean source repository. "
            "Commit or stash local changes first."
        )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _api_call(
    forge: Forge,
    hostname: str,
    endpoint: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    executable = "gh" if forge is Forge.GITHUB else "glab"
    if shutil.which(executable) is None:
        raise PublishError(f"{executable} is not installed or is not available in PATH.")
    command = [
        executable,
        "api",
        endpoint,
        "--hostname",
        hostname,
        "--method",
        method,
    ]
    encoded_payload: str | None = None
    if payload is not None:
        command.extend(["--input", "-"])
        encoded_payload = json.dumps(payload)
    result = subprocess.run(
        command,
        input=encoded_payload,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise PublishError(f"{forge.value} API request failed: {details}")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PublishError(f"{forge.value} API returned invalid JSON.") from error
    if not isinstance(response, dict):
        raise PublishError(f"{forge.value} API returned an unexpected response.")
    return response


def _create_remote(
    request: PublishRequest, authenticated_user: AuthenticatedUser
) -> tuple[str, str]:
    namespace, name = validate_publish_request(request)
    if request.forge is Forge.GITHUB:
        endpoint = (
            "user/repos"
            if namespace.casefold() == authenticated_user.username.casefold()
            else f"orgs/{namespace}/repos"
        )
        response = _api_call(
            request.forge,
            authenticated_user.hostname,
            endpoint,
            method="POST",
            payload={"name": name, "visibility": request.visibility.value},
        )
        ssh_url = response.get("ssh_url")
        web_url = response.get("html_url")
    else:
        namespace_response = _api_call(
            request.forge,
            authenticated_user.hostname,
            f"namespaces/{quote(namespace, safe='')}",
        )
        namespace_id = namespace_response.get("id")
        if not isinstance(namespace_id, int):
            raise PublishError(f"Could not resolve GitLab namespace {namespace}.")
        response = _api_call(
            request.forge,
            authenticated_user.hostname,
            "projects",
            method="POST",
            payload={
                "name": name,
                "path": name,
                "namespace_id": namespace_id,
                "visibility": request.visibility.value,
            },
        )
        ssh_url = response.get("ssh_url_to_repo")
        web_url = response.get("web_url")

    if not isinstance(ssh_url, str) or not isinstance(web_url, str):
        raise PublishError(f"{request.forge.value} API response did not include repository URLs.")
    return ssh_url, web_url


def _commit_conversion(repository: Path, forge: Forge) -> None:
    staged = _git(
        repository,
        "add",
        "--all",
        "--",
        ".",
        ":(exclude).forge-switcheroo-report.json",
    )
    if staged.returncode != 0:
        raise PublishError(f"Could not stage converted files: {staged.stderr.strip()}")
    changed = _git(repository, "diff", "--cached", "--quiet")
    if changed.returncode == 0:
        return
    if changed.returncode != 1:
        raise PublishError(f"Could not inspect converted files: {changed.stderr.strip()}")
    committed = _git(repository, "commit", "-m", f"chore: migrate project to {forge.value}")
    if committed.returncode != 0:
        raise PublishError(
            "Could not commit converted files. Ensure Git user.name and user.email are configured. "
            f"{committed.stderr.strip()}"
        )


def _record_publication(repository: Path, result: PublishResult) -> None:
    report_path = repository / ".forge-switcheroo-report.json"
    if not report_path.is_file():
        return
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(report, dict):
        return
    report["publication"] = {
        "repository": result.repository,
        "web_url": result.web_url,
        "ssh_url": result.ssh_url,
        "branch": result.branch,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def publish_repository(
    repository: Path,
    branch: str,
    request: PublishRequest,
    authenticated_user: AuthenticatedUser,
) -> PublishResult:
    """Create an empty remote repository and push only the converted primary branch."""
    validate_publish_request(request)
    if request.forge is not authenticated_user.forge:
        raise PublishError("Authenticated forge does not match the target forge.")
    if request.hostname.strip().lower() != authenticated_user.hostname:
        raise PublishError("Authenticated hostname does not match the target hostname.")
    _commit_conversion(repository, request.forge)
    ssh_url, web_url = _create_remote(request, authenticated_user)

    added = _git(repository, "remote", "add", "origin", ssh_url)
    if added.returncode != 0:
        raise PublishError(
            f"Remote repository was created at {web_url}, but origin could not be added: "
            f"{added.stderr.strip()}"
        )
    pushed = _git(repository, "push", "--set-upstream", "origin", branch)
    if pushed.returncode != 0:
        raise PublishError(
            f"Remote repository was created at {web_url}, but the {branch} push failed: "
            f"{pushed.stderr.strip()}"
        )
    result = PublishResult(request.repository, web_url, ssh_url, branch)
    _record_publication(repository, result)
    return result
