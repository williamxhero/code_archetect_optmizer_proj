from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from code_architect_optimizer.analyzers.base import MetricObservation, RawAnalyzerResult
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.reports import render_json
from code_architect_optimizer.scan import scan_repository


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


def test_changed_only_scans_diff_paths_and_keeps_commit_provenance(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    changed = tmp_path / "src" / "changed.py"
    stable = tmp_path / "src" / "stable.py"
    changed.write_text("initial\n", encoding="utf-8")
    stable.write_text("stable\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "baseline"], cwd=tmp_path, check=True)
    changed.write_text("changed\n", encoding="utf-8")

    analyzer = FakeAnalyzer("scc", [
        MetricObservation("file", "src/changed.py", {"nloc": 10}),
        MetricObservation("file", "src/stable.py", {"nloc": 20}),
    ])
    report = scan_repository(
        tmp_path,
        config={"project": {"name": "changed-project"}},
        analyzers=[analyzer],
        runner=fake_runner,
        changed_only=True,
        write_reports=False,
    )

    assert [metric.path for metric in report.files] == ["src/changed.py"]
    assert report.commit != "unknown"
    assert report.files[0].provenance.commit == report.commit


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
