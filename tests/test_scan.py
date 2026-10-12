from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from code_architect_optimizer.analyzers.base import MetricObservation, RawAnalyzerResult, run_analyzer
from code_architect_optimizer.classification.file_classifier import detect_language
from code_architect_optimizer.domain.models import ScanContext
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.reports import render_json, read_json_report
from code_architect_optimizer.scan import scan_repository
from tests.fixtures import materialize_project_fixture


class FakeAnalyzer:
    def __init__(self, name: str, observations=None, *, available: bool = True, stdout: str = ""):
        self.name = name
        self.observations = observations or []
        self.available = available
        self.stdout = stdout

    def parse(self, result, context):
        if self.name == "broken":
            raise ValueError("invalid analyzer payload")
        return self.observations


def fake_runner(analyzer, context, timeout):
    return RawAnalyzerResult(
        name=analyzer.name,
        available=analyzer.available,
        stdout=analyzer.stdout,
        stderr="password=must-not-enter-report",
        version=f"{analyzer.name}-1",
        error="tool not found on PATH" if not analyzer.available else "",
    )


def test_scan_merges_observations_scores_risks_and_writes_public_artifacts(tmp_path: Path) -> None:
    analyzers = [
        FakeAnalyzer("scc", [
            MetricObservation("file", "src/hot.py", {"language": "python", "loc": 700, "nloc": 601}),
            MetricObservation("file", "generated/client.py", {"language": "python", "loc": 900, "nloc": 800}),
        ]),
        FakeAnalyzer("lizard", [
            MetricObservation("function", "src/hot.py", {
                "qualified_name": "hot", "start_line": 12, "end_line": 80,
                "nloc": 51, "cyclomatic_complexity": 11,
            }),
        ]),
        FakeAnalyzer("jscpd", [
            MetricObservation("duplication", "src/hot.py", {"duplicated_lines": 100}),
        ]),
        FakeAnalyzer("git-history", [
            MetricObservation("churn", "src/hot.py", {"churn_90d": 10, "contributors_90d": 3}),
        ]),
        FakeAnalyzer(
            "missing",
            [MetricObservation("file", "stale.py", {"nloc": 999})],
            available=False,
        ),
        FakeAnalyzer("broken", stdout="not-json"),
    ]

    report = scan_repository(
        tmp_path,
        config={
            "project": {"name": "fake-project"},
            "scan": {"exclude": ["generated/**"]},
            "thresholds": {
                "file_nloc_review": 300,
                "file_nloc_high": 500,
                "function_nloc_review": 50,
                "cyclomatic_complexity_review": 10,
                "duplication_ratio_review": 0.10,
            },
        },
        config_hash="config-digest",
        analyzers=analyzers,
        runner=fake_runner,
    )

    assert isinstance(report, ReportDocument)
    assert report.repository == "fake-project"
    assert report.config_hash == "config-digest"
    assert [metric.path for metric in report.files] == ["src/hot.py"]
    metric = report.files[0]
    assert metric.category == "production"
    assert metric.duplication_ratio == pytest.approx(100 / 601, abs=1e-6)
    assert metric.churn_90d == 10
    assert report.functions[0].qualified_name == "hot"
    assert report.risks[0].path == "src/hot.py"
    assert report.risks[0].risk_score == 7
    assert report.risks[0].change_pressure == 3
    assert report.risks[0].refactor_priority == 21
    assert report.unavailable_tools == ["missing"]
    statuses = {(item.source_tool, item.raw_value, item.excerpt) for item in report.evidence if item.kind == "analyzer-status"}
    assert any(tool == "missing" and status == "unavailable" for tool, status, _ in statuses)
    assert any(tool == "broken" and status == "parse-incomplete" and "could not be parsed" in excerpt
               for tool, status, excerpt in statuses)

    rendered = render_json(report)
    assert "must-not-enter-report" not in rendered
    assert (tmp_path / ".code-health" / "raw" / "scc.out").is_file()
    assert (tmp_path / ".code-health" / "reports" / "report.json").is_file()
    assert (tmp_path / ".code-health" / "reports" / "report.md").is_file()


@pytest.mark.parametrize(("duplicated_lines", "nloc", "expected_ratio"), [
    (283, 100, 1.0),
    (2037, 1000, 1.0),
    (50, 100, 0.5),
    (100, 100, 1.0),
    (0, 100, 0.0),
    (-10, 100, 0.0),
    (10, 0, 0.0),
])
def test_scan_bounds_duplication_ratio(
    tmp_path: Path, duplicated_lines: int, nloc: int, expected_ratio: float,
) -> None:
    analyzers = [
        FakeAnalyzer("scc", [
            MetricObservation("file", "src/app.py", {"nloc": nloc}),
        ]),
        FakeAnalyzer("jscpd", [
            MetricObservation("duplication", "src/app.py", {"duplicated_lines": duplicated_lines}),
        ]),
    ]

    report = scan_repository(
        tmp_path,
        config={"project": {"name": "duplication-bounds"}},
        analyzers=analyzers,
        runner=fake_runner,
        write_reports=False,
    )

    assert report.files[0].duplication_ratio == expected_ratio


def test_scan_excludes_code_health_artifacts_from_analyzer_observations(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer("jscpd", [
        MetricObservation("file", ".code-health/raw/jscpd.out", {"nloc": 8}),
        MetricObservation("file", "src/app.py", {"nloc": 8}),
    ])

    report = scan_repository(
        tmp_path,
        config={"project": {"name": "work-dir-exclusion"}},
        analyzers=[analyzer],
        runner=fake_runner,
        write_reports=False,
    )

    assert [metric.path for metric in report.files] == ["src/app.py"]


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=path, check=True)


def _commit(path: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", message], cwd=path, check=True)


def _scan_changed_fixture(path: Path, observations: list[MetricObservation]):
    return scan_repository(
        path,
        config={"project": {"name": "changed-project"}},
        analyzers=[FakeAnalyzer("scc", observations)],
        runner=fake_runner,
        changed_only=True,
        write_reports=False,
    )


def test_changed_only_scans_clean_branch_delta_and_keeps_commit_provenance(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "changed.py").write_text("initial\n", encoding="utf-8")
    (tmp_path / "src" / "stable.py").write_text("stable\n", encoding="utf-8")
    _init_git_repo(tmp_path)
    _commit(tmp_path, "baseline")
    subprocess.run(["git", "switch", "--quiet", "-c", "feature"], cwd=tmp_path, check=True)
    (tmp_path / "src" / "changed.py").write_text("changed\n", encoding="utf-8")
    _commit(tmp_path, "change")

    report = _scan_changed_fixture(tmp_path, [
        MetricObservation("file", "src/changed.py", {"nloc": 10}),
        MetricObservation("file", "src/stable.py", {"nloc": 20}),
    ])

    assert [metric.path for metric in report.files] == ["src/changed.py"]
    assert report.commit != "unknown"
    assert report.files[0].provenance.commit == report.commit


def test_changed_only_merges_staged_unstaged_and_untracked_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    for name in ("committed.py", "staged.py", "unstaged.py", "untracked.py", "stable.py"):
        (src / name).write_text("initial\n", encoding="utf-8")
    _init_git_repo(tmp_path)
    _commit(tmp_path, "baseline")
    subprocess.run(["git", "switch", "--quiet", "-c", "feature"], cwd=tmp_path, check=True)
    (src / "committed.py").write_text("branch change\n", encoding="utf-8")
    _commit(tmp_path, "branch change")
    (src / "staged.py").write_text("staged change\n", encoding="utf-8")
    subprocess.run(["git", "add", str(src / "staged.py")], cwd=tmp_path, check=True)
    (src / "unstaged.py").write_text("unstaged change\n", encoding="utf-8")
    (src / "untracked.py").write_text("new file\n", encoding="utf-8")

    report = _scan_changed_fixture(tmp_path, [
        MetricObservation("file", f"src/{name}", {"nloc": index})
        for index, name in enumerate(("committed.py", "staged.py", "unstaged.py", "untracked.py", "stable.py"), 1)
    ])

    assert [metric.path for metric in report.files] == [
        "src/committed.py", "src/staged.py", "src/unstaged.py", "src/untracked.py",
    ]


def test_changed_only_includes_deterministic_python_dependency_closure(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "changed.py").write_text("from helper import value\n", encoding="utf-8")
    (src / "helper.py").write_text("from leaf import value\n", encoding="utf-8")
    (src / "leaf.py").write_text("value = 1\n", encoding="utf-8")
    (src / "unrelated.py").write_text("value = 2\n", encoding="utf-8")
    _init_git_repo(tmp_path)
    _commit(tmp_path, "baseline")
    subprocess.run(["git", "switch", "--quiet", "-c", "feature"], cwd=tmp_path, check=True)
    (src / "changed.py").write_text("from helper import value\nchanged = value\n", encoding="utf-8")
    _commit(tmp_path, "change")

    report = _scan_changed_fixture(tmp_path, [
        MetricObservation("file", f"src/{name}.py", {"nloc": index})
        for index, name in enumerate(("changed", "helper", "leaf", "unrelated"), 1)
    ])

    assert [metric.path for metric in report.files] == [
        "src/changed.py", "src/helper.py", "src/leaf.py",
    ]


def test_changed_only_falls_back_to_full_scan_without_a_usable_git_base(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer("scc", [
        MetricObservation("file", "src/one.py", {"nloc": 1}),
        MetricObservation("file", "src/two.py", {"nloc": 2}),
    ])

    report = scan_repository(
        tmp_path,
        config={"project": {"name": "no-git"}},
        analyzers=[analyzer],
        runner=fake_runner,
        changed_only=True,
        write_reports=False,
    )

    assert [metric.path for metric in report.files] == ["src/one.py", "src/two.py"]
    assert any(
        item.kind == "scan-selection" and item.raw_value == "full-scan-fallback"
        for item in report.evidence
    )


def test_missing_phase_one_capabilities_are_reported_without_stopping_scan(tmp_path: Path) -> None:
    names = ["scc", "lizard", "jscpd", "git-history"]
    analyzers = [FakeAnalyzer(name, available=False) for name in names]

    report = scan_repository(
        tmp_path,
        config={"project": {"name": "missing-tools"}},
        analyzers=analyzers,
        runner=fake_runner,
        write_reports=False,
    )

    assert report.files == []
    assert report.unavailable_tools == sorted(names)
    statuses = {
        item.source_tool: item
        for item in report.evidence
        if item.kind == "analyzer-status"
    }
    assert set(statuses) == set(names)
    assert all(item.raw_value == "unavailable" for item in statuses.values())
    assert all(item.provenance is not None and not item.provenance.parse_complete for item in statuses.values())


def test_failure_states_keep_bounded_status_evidence_and_redact_process_data(tmp_path: Path) -> None:
    analyzers = [
        FakeAnalyzer("timeout", stdout="timeout-output" * 2_000),
        FakeAnalyzer("nonzero", stdout="nonzero-output"),
        FakeAnalyzer("broken", stdout="malformed-output"),
    ]

    def failure_runner(analyzer, context, timeout):
        if analyzer.name == "timeout":
            return RawAnalyzerResult(
                name=analyzer.name,
                available=True,
                stdout=analyzer.stdout,
                stderr="password=do-not-publish",
                version="fixture-1",
                error="timeout after 1s",
            )
        if analyzer.name == "nonzero":
            return RawAnalyzerResult(
                name=analyzer.name,
                available=True,
                stdout=analyzer.stdout,
                stderr="token=do-not-publish",
                version="fixture-1",
                exit_code=7,
            )
        return RawAnalyzerResult(
            name=analyzer.name,
            available=True,
            stdout=analyzer.stdout,
            stderr="secret=do-not-publish",
            version="fixture-1",
        )

    report = scan_repository(
        tmp_path,
        config={"project": {"name": "failure-states"}},
        analyzers=analyzers,
        runner=failure_runner,
        write_reports=False,
    )

    statuses = {
        item.source_tool: item
        for item in report.evidence
        if item.kind == "analyzer-status"
    }
    assert {item.raw_value for item in statuses.values()} == {"parse-incomplete"}
    assert "timeout after 1s" in statuses["timeout"].excerpt
    assert "code 7" in statuses["nonzero"].excerpt
    assert "could not be parsed" in statuses["broken"].excerpt
    assert all(len(item.excerpt) <= 500 for item in statuses.values())
    assert all(item.provenance is not None and not item.provenance.parse_complete for item in statuses.values())

    rendered = render_json(report)
    assert "do-not-publish" not in rendered
    assert len((tmp_path / ".code-health" / "raw" / "timeout.out").read_text(encoding="utf-8")) > 10_000


def test_runner_degrades_capability_setup_errors_to_unavailable(tmp_path: Path) -> None:
    class BrokenCapability:
        name = "broken-capability"

        def is_available(self) -> bool:
            raise RuntimeError("capability check failed")

    result = run_analyzer(BrokenCapability(), ScanContext(repo_root=str(tmp_path)))

    assert result.available is False
    assert result.error == "tool not found on PATH"
    assert result.raw_path.endswith("broken-capability.out")


def test_fixture_scan_produces_schema_valid_deterministic_categorized_report(tmp_path: Path) -> None:
    fixture = materialize_project_fixture(tmp_path / "fixture")
    nloc = {
        "src/calculations.py": 700,
        "src/stable.py": 20,
        "tests/calculation_checks.py": 120,
        "generated/client.py": 50,
        "vendor/dependency.py": 40,
        "config/settings.toml": 10,
    }
    analyzers = [
        FakeAnalyzer("scc", [
            MetricObservation("file", path, {
                "language": detect_language(path), "loc": value + 10, "nloc": value,
            })
            for path, value in nloc.items()
        ]),
        FakeAnalyzer("lizard", [MetricObservation("function", "src/calculations.py", {
            "qualified_name": "complex_decision", "start_line": 4, "end_line": 21,
            "nloc": 51, "cyclomatic_complexity": 11,
        })]),
        FakeAnalyzer("jscpd", [MetricObservation("duplication", "src/calculations.py", {
            "duplicated_lines": 100,
        })]),
        FakeAnalyzer("git-history", [MetricObservation("churn", "src/calculations.py", {
            "churn_90d": 10, "contributors_90d": 3,
        })]),
    ]

    config = {
        "project": {"name": "fixture-project"},
        "thresholds": {
            "file_nloc_review": 300,
            "file_nloc_high": 500,
            "function_nloc_review": 50,
            "cyclomatic_complexity_review": 10,
            "duplication_ratio_review": 0.10,
        },
    }
    first = scan_repository(
        fixture,
        config=config,
        config_hash="fixture-config",
        analyzers=analyzers,
        runner=fake_runner,
    )
    first_bytes = (fixture / ".code-health" / "reports" / "report.json").read_bytes()
    second = scan_repository(
        fixture,
        config=config,
        config_hash="fixture-config",
        analyzers=analyzers,
        runner=fake_runner,
    )
    second_bytes = (fixture / ".code-health" / "reports" / "report.json").read_bytes()

    parsed = ReportDocument.model_validate_json(first_bytes)
    assert parsed.schema_version == 1
    assert first_bytes == second_bytes
    assert render_json(first) == render_json(second)
    assert {metric.path: metric.category for metric in first.files} == {
        "src/calculations.py": "production",
        "src/stable.py": "production",
        "tests/calculation_checks.py": "test",
        "generated/client.py": "generated",
        "vendor/dependency.py": "vendor",
        "config/settings.toml": "config",
    }
    assert [risk.path for risk in first.risks[:2]] == ["src/calculations.py", "config/settings.toml"]
    assert first.risks[0].refactor_priority == 21
    assert all(metric.provenance.config_hash == "fixture-config" for metric in first.files)
    assert all(metric.provenance.parse_complete for metric in first.files)
    loaded = read_json_report(fixture / ".code-health" / "reports" / "report.json")
    assert render_json(loaded) == second_bytes.decode("utf-8")
