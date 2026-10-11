from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from code_architect_optimizer.analyzers.base import run_analyzer
from code_architect_optimizer.analyzers.git_history import GitHistoryAnalyzer
from code_architect_optimizer.classification.file_classifier import classify, detect_language
from code_architect_optimizer.domain.models import ScanContext
from tests.fixtures import (
    load_expected_fixture_data,
    materialize_git_history_fixture,
    materialize_project_fixture,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_project_fixture_materializes_expected_categories_and_samples(tmp_path) -> None:
    expected = load_expected_fixture_data()["project"]
    destination = materialize_project_fixture(tmp_path / "project")

    assert not (FIXTURE_ROOT / "project" / ".git").exists()
    assert not (destination / ".git").exists()
    for relative_path, values in expected["files"].items():
        assert (destination / relative_path).is_file()
        assert classify(relative_path) == values["category"]
        assert detect_language(relative_path) == values["language"]

    source = (destination / expected["complex_function"]["path"]).read_text(encoding="utf-8")
    assert f"def {expected['complex_function']['qualified_name']}" in source
    assert source.count("    if ") >= expected["complex_function"]["minimum_cyclomatic_complexity"] - 2

    duplicate = expected["duplicate_functions"]
    assert all(f"def {name}" in source for name in duplicate["qualified_names"])
    body = "    for value in values:\n        if value < 0:\n            result.append(0)\n        else:\n            result.append(value)"
    assert source.count(body) == 2
    assert len(body.splitlines()) >= duplicate["minimum_matching_body_lines"]


def test_expected_fixture_data_is_valid_json() -> None:
    payload = json.loads((FIXTURE_ROOT / "expected.json").read_text(encoding="utf-8"))
    assert payload["git_history"]["observations"]["src/metrics.py"]["churn_90d"] == 3


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required for history fixture")
def test_git_history_fixture_materializes_deterministic_window(tmp_path) -> None:
    expected = load_expected_fixture_data()["git_history"]
    destination = materialize_git_history_fixture(tmp_path / "history")
    context = ScanContext(repo_root=str(destination))

    result = run_analyzer(GitHistoryAnalyzer(), context)
    observations = GitHistoryAnalyzer().parse(result, context)
    actual = {observation.path: observation.data for observation in observations}
    history = subprocess.run(
        ["git", "log", "--format=COMMIT:%an", "--name-only"],
        cwd=destination,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    actual_commits = []
    current = None
    for line in history.splitlines():
        if line.startswith("COMMIT:"):
            if current is not None:
                actual_commits.append(current)
            current = {"author": line.removeprefix("COMMIT:"), "paths": []}
        elif line and current is not None:
            current["paths"].append(line)
    if current is not None:
        actual_commits.append(current)
    for commit in actual_commits:
        commit["paths"].sort()

    assert actual == expected["observations"]
    assert actual_commits == list(reversed(expected["commits"]))
    assert (destination / ".git").is_dir()
    assert not (FIXTURE_ROOT / "git_history" / ".git").exists()
