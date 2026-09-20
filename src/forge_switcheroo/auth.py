from __future__ import annotations

import json
import shutil
import subprocess

from forge_switcheroo.models import AuthenticatedUser, Forge


class AuthenticationError(RuntimeError):
    """Raised when a forge CLI cannot provide authenticated API access."""


def default_hostname(forge: Forge) -> str:
    return "github.com" if forge is Forge.GITHUB else "gitlab.com"


def _validate_hostname(hostname: str) -> str:
    value = hostname.strip().lower()
    if not value or "://" in value or "/" in value or any(char.isspace() for char in value):
        raise AuthenticationError(
            "The hostname must not contain a scheme, path, or whitespace "
            "(example: gitlab.example.com)."
        )
    return value


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _failure_message(result: subprocess.CompletedProcess[str]) -> str:
    details = result.stderr.strip() or result.stdout.strip()
    return details.splitlines()[-1] if details else "The command returned a non-zero status."


def check_authentication(forge: Forge, hostname: str) -> AuthenticatedUser:
    """Verify CLI authentication and perform a real API request without reading a token."""
    host = _validate_hostname(hostname)
    executable = "gh" if forge is Forge.GITHUB else "glab"
    if shutil.which(executable) is None:
        raise AuthenticationError(f"{executable} is not installed or is not available in PATH.")

    status_command = [executable, "auth", "status", "--hostname", host]
    if forge is Forge.GITHUB:
        status_command.insert(3, "--active")
    status = _run(status_command)
    if status.returncode != 0:
        login_command = f"{executable} auth login --hostname {host}"
        raise AuthenticationError(
            f"No valid {forge.value} authentication was found for {host}. "
            f"Run `{login_command}` first. {_failure_message(status)}"
        )

    identity = _run([executable, "api", "user", "--hostname", host])
    if identity.returncode != 0:
        raise AuthenticationError(
            f"Authentication exists for {host}, but the API request failed: "
            f"{_failure_message(identity)}"
        )
    try:
        payload = json.loads(identity.stdout)
        key = "login" if forge is Forge.GITHUB else "username"
        username = payload[key]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AuthenticationError(
            f"The {executable} API returned an unexpected user response for {host}."
        ) from error
    if not isinstance(username, str) or not username:
        raise AuthenticationError(f"The {executable} API did not return a valid username.")
    return AuthenticatedUser(forge=forge, hostname=host, username=username)
