# forge-switcheroo

`forge-switcheroo` prepares a safe, local copy of a GitHub repository for GitLab, or a
GitLab repository for GitHub.

The project is currently a **local MVP**: it copies the repository and its Git history,
neutralizes the `origin` remote in the copy, converts selected components where possible,
and writes a report. It does not create the remote repository or migrate issues,
pull/merge requests, secrets, or CI variables through the APIs yet.

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
3. an optional API authentication preflight using `gh` or `glab`;
4. the new project name and destination parent directory;
5. optional transformations;
6. a summary before any files are written.

An explicit command is also available for scripts:

```console
forge-switcheroo migrate ./my-project ./output/my-project-gitlab \
  --target gitlab --feature ci --feature templates
```

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

The preflight checks the relevant CLI authentication and makes an authenticated `/user`
API request. SSH credentials remain responsible for Git clone/fetch/push operations;
they do not authenticate HTTP API calls.

## MVP transformations

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
uv run pytest
```
