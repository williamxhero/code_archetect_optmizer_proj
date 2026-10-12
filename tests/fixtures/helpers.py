from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Final

FIXTURE_ROOT: Final = Path(__file__).parent
PROJECT_FIXTURE_ROOT: Final = FIXTURE_ROOT / "project"
GIT_HISTORY_FIXTURE_ROOT: Final = FIXTURE_ROOT / "git_history"
TYPESCRIPT_FIXTURE_ROOT: Final = FIXTURE_ROOT / "typescript"
EXPECTED_FIXTURE_DATA: Final = FIXTURE_ROOT / "expected.json"


def load_expected_fixture_data() -> dict:
    return json.loads(EXPECTED_FIXTURE_DATA.read_text(encoding="utf-8"))


def materialize_project_fixture(destination: Path) -> Path:
    """Copy the analyzer project fixture to a new temporary directory."""
    destination = Path(destination)
    shutil.copytree(PROJECT_FIXTURE_ROOT, destination)
    return destination


def materialize_typescript_fixture(destination: Path) -> Path:
    """Copy the deterministic TypeScript analyzer fixture to a new directory."""
    destination = Path(destination)
    shutil.copytree(TYPESCRIPT_FIXTURE_ROOT, destination)
    return destination


def _run_git(destination: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=destination,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(destination: Path, *, author: str, days_ago: int, message: str) -> None:
    timestamp = (date.today() - timedelta(days=days_ago)).isoformat() + "T12:00:00+0000"
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": f"{author.lower().replace(' ', '.')}@example.test",
            "GIT_COMMITTER_NAME": author,
            "GIT_COMMITTER_EMAIL": f"{author.lower().replace(' ', '.')}@example.test",
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_DATE": timestamp,
        }
    )
    _run_git(destination, "commit", "-m", message, env=env)


def materialize_git_history_fixture(destination: Path) -> Path:
    """Create a fresh Git repository with deterministic trailing-window history."""
    destination = Path(destination)
    shutil.copytree(GIT_HISTORY_FIXTURE_ROOT, destination)
    _run_git(destination, "init", "--quiet", "--initial-branch=main")
    _run_git(destination, "config", "user.name", "Fixture Committer")
    _run_git(destination, "config", "user.email", "fixture@example.test")

    _run_git(destination, "add", "--all")
    _commit(destination, author="Alice Example", days_ago=60, message="seed fixture files")

    metrics = destination / "src" / "metrics.py"
    metrics.write_text(
        metrics.read_text(encoding="utf-8") + "\ndef second_metric(value: int) -> int:\n    return value * 2\n",
        encoding="utf-8",
    )
    _run_git(destination, "add", "src/metrics.py")
    _commit(destination, author="Bob Example", days_ago=30, message="add second metric")

    metrics.write_text(
        metrics.read_text(encoding="utf-8") + "\ndef third_metric(value: int) -> int:\n    return value - 1\n",
        encoding="utf-8",
    )
    readme = destination / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "History is intentionally reproducible.\n",
        encoding="utf-8",
    )
    _run_git(destination, "add", "README.md", "src/metrics.py")
    _commit(destination, author="Carol Example", days_ago=1, message="update fixture history")
    return destination
