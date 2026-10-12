from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from code_architect_optimizer.cli import app
from code_architect_optimizer.domain.models import Finding
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.reports import render_sarif, write_report_artifacts


def test_sarif_maps_rules_severity_locations_and_evidence() -> None:
    report = ReportDocument(
        commit="abc123",
        config_hash="cfg456",
        findings=[Finding(
            rule_id="function.complexity.high", severity="high", path="src\\a #%.py",
            line=12, metric="cyclomatic_complexity", actual=15, threshold=10,
            evidence_source="lizard", message="Review complexity",
        ), Finding(rule_id="file.nloc.review", severity="medium", path="src/b.py", line=0)],
    )
    sarif = json.loads(render_sarif(report))
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "code-health"
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == ["file.nloc.review", "function.complexity.high"]
    result = run["results"][0]
    assert result["ruleId"] == "function.complexity.high"
    assert result["ruleIndex"] == 1
    assert result["level"] == "error"
    assert result["message"]["text"] == "Review complexity"
    assert result["locations"][0]["physicalLocation"] == {
        "artifactLocation": {"uri": "src/a%20%23%25.py"}, "region": {"startLine": 12},
    }
    assert result["properties"]["actual"] == 15
    assert result["properties"]["threshold"] == 10
    assert result["properties"]["evidence_source"] == "lizard"
    file_result = run["results"][1]
    assert file_result["level"] == "warning"
    assert file_result["locations"][0]["physicalLocation"]["region"]["startLine"] == 1
    assert file_result["properties"]["original_line"] == 0
    assert file_result["message"]["text"]
    assert run["properties"]["commit"] == "abc123"


@pytest.mark.parametrize(("severity", "level"), [
    ("critical", "error"), ("high", "error"), ("medium", "warning"),
    ("low", "note"), ("info", "note"),
])
def test_sarif_severity_mapping(severity, level) -> None:
    sarif = json.loads(render_sarif(ReportDocument(findings=[
        Finding(rule_id="sample", path="sample.py", severity=severity),
    ])))
    assert sarif["runs"][0]["results"][0]["level"] == level


@pytest.mark.parametrize("path", ["", ".", "/outside.py", "C:\\outside.py", "../outside.py", "src/../../outside.py"])
def test_sarif_rejects_non_repository_locations(path) -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        render_sarif(ReportDocument(findings=[Finding(rule_id="sample", path=path)]))


def test_empty_sarif_keeps_analyzer_coverage_diagnostics() -> None:
    report = ReportDocument(unavailable_tools=["scc"])
    run = json.loads(render_sarif(report))["runs"][0]
    assert run["results"] == []
    assert run["tool"]["driver"]["rules"] == []
    assert run["properties"]["unavailable_tools"] == ["scc"]


def test_sarif_cli_uses_saved_json_without_markdown_or_analyzers(tmp_path) -> None:
    report = ReportDocument(findings=[Finding(rule_id="sample", path="sample.py", severity="low")])
    paths = write_report_artifacts(report, tmp_path)
    paths["markdown"].unlink()
    runner = CliRunner()
    first = runner.invoke(app, ["report", "--format", "sarif", str(tmp_path)])
    second = runner.invoke(app, ["report", "--format", "sarif", str(tmp_path)])
    assert first.exit_code == second.exit_code == 0
    assert first.output == second.output == render_sarif(report)
    assert len(json.loads(first.output)["runs"][0]["results"]) == 1


@pytest.mark.parametrize("contents", [None, "not json", '{"schema_version": 999}'])
def test_sarif_cli_reports_missing_or_incompatible_input(tmp_path, contents) -> None:
    if contents is not None:
        directory = tmp_path / ".code-health" / "reports"
        directory.mkdir(parents=True)
        (directory / "report.json").write_text(contents, encoding="utf-8")
    result = CliRunner().invoke(app, ["report", "--format", "sarif", str(tmp_path)])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Traceback" not in result.output
