[![CI](https://github.com/ccasatejada/forge-switcheroo/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ccasatejada/forge-switcheroo/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet?logo=astral&logoColor=white)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
![mypy](https://img.shields.io/badge/type%20checker-mypy-blue?logo=python&logoColor=white)
![pytest](https://img.shields.io/badge/tests-pytest-blue?logo=pytest&logoColor=white)
![Typer](https://img.shields.io/badge/CLI-Typer-009485)

# forge-switcheroo

`forge-switcheroo` converts a GitHub repository for GitLab, or a GitLab repository for
GitHub. It can keep the result local or create the target repository and push the
converted primary branch.

The source repository is never overwritten. The converted repository is created in a new
directory, and remote publishing is always optional. Forge-specific server data such as
issues, pull/merge requests, secrets, and CI variables is not migrated yet.

## Installation

Python 3.11 or newer is required. The recommended installation uses
[uv](https://docs.astral.sh/uv/) and exposes the command globally without activating a
virtual environment:

```console
git clone https://github.com/ccasatejada/forge-switcheroo.git
cd forge-switcheroo
uv tool install .
```

Alternatively, install the local checkout with `pipx`:

```console
pipx install .
```

Both command names are equivalent and available directly from the terminal:

```console
forge-switcheroo --help
fswitch --help
```

If the shell cannot find the commands after an `uv` installation, run
`uv tool update-shell`, then open a new terminal.

## Usage

Running either command without arguments opens the interactive wizard:

```console
forge-switcheroo
# or
fswitch
```

The wizard provides:

1. source directory selection with path completion;
2. target forge selection, defaulting to the opposite forge;
3. the new project name and destination parent directory;
4. optional transformations;
5. optional remote repository creation and `main`/`master` push;
6. an API authentication preflight when remote publishing is enabled;
7. a summary before any files or remote resources are created.

An explicit command is also available for scripts:

```console
forge-switcheroo migrate ./my-project ./output/my-project-gitlab \
  --target gitlab --feature ci --feature templates
```

Add `--publish` to create the target repository and push the converted primary branch:

```console
forge-switcheroo migrate ./my-project ./output/my-project-gitlab \
  --target gitlab \
  --feature ci \
  --feature templates \
  --publish \
  --hostname gitlab.example.com \
  --repository my-group/my-project \
  --visibility private
```

When `--repository` is omitted, it defaults to the authenticated user's namespace and
the destination directory name. `--hostname` defaults to `github.com` or `gitlab.com`.

To inspect a repository without changing it:

```console
forge-switcheroo inspect ./my-project
```

Display the installed version with:

```console
forge-switcheroo --version
```

## Authentication

API authentication is delegated to the official forge CLIs. `forge-switcheroo` never
requests, reads, stores, or prints their tokens:

```console
gh auth login --hostname github.com
glab auth login --hostname gitlab.example.com

forge-switcheroo auth-check github
forge-switcheroo auth-check gitlab --hostname gitlab.example.com
```

Authentication is optional for local conversion and required only with `--publish`. The
preflight checks the relevant CLI authentication and makes an authenticated `/user` API
request. The official CLI then creates the repository through the API, while SSH
credentials are used by Git for the push.

## Publishing behavior

Remote publishing deliberately migrates only one primary branch:

- `main` is preferred when both `main` and `master` exist;
- `master` is used when no `main` branch exists;
- repositories with neither branch are rejected;
- tags and secondary branches are not pushed;
- the source repository must have no staged, modified, or untracked files;
- converted files are committed as `chore: migrate project to <forge>`;
- `.forge-switcheroo-report.json` remains local and is not committed;
- the original remote is retained as `source`, while the new repository becomes
  `origin`.

If repository creation succeeds but the Git push fails, the CLI reports the remote URL
and preserves the converted local directory for recovery. It never deletes the remote
repository automatically.

## Transformations

- `ci` generates a conservative target pipeline based on the detected language. The
  source file is preserved for manual review.
- `templates` copies issue templates to the target forge convention.
- the copied repository's `origin` remote is renamed to `source`, preventing accidental
  pushes to the original repository.
- `.forge-switcheroo-report.json` records all actions and warnings.

Arbitrary conversion between GitHub Actions and GitLab CI cannot be fully reliable:
their syntax, runners, secrets, and execution models differ. The generated pipeline is
therefore a readable starting point, never presented as equivalent.

## Quality checks

Create the development environment, including Ruff, mypy, and pytest:

```console
uv sync --extra dev
```

```console
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov=forge_switcheroo --cov-report=term-missing
```

## Continuous integration

GitHub Actions runs the following checks on every push and pull request targeting
`main`:

- Ruff linting and formatting;
- strict mypy type checking;
- tests on Python 3.11, 3.12, 3.13, and 3.14;
- package coverage with a 60% minimum;
- wheel and source distribution builds;
- smoke tests for both `forge-switcheroo` and `fswitch` installed commands.

Test and coverage XML reports, as well as the built distributions, are retained as
workflow artifacts for seven days. The workflow requires no repository secrets.
