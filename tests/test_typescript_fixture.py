from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from code_architect_optimizer.cli import app
from code_architect_optimizer.analyzers.base import MetricObservation, RawAnalyzerResult
from code_architect_optimizer.classification.file_classifier import classify, detect_language
from code_architect_optimizer.domain.models import ScanContext
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.reports import read_json_report, render_json, render_markdown, render_sarif
from code_architect_optimizer.scan import scan_repository
from tests.fixtures import load_expected_fixture_data, materialize_typescript_fixture


class ControlledAnalyzer:
    def __init__(self, name: str, observations: list[MetricObservation]) -> None:
        self.name = name
        self.observations = observations

    def parse(self, result: RawAnalyzerResult, context: ScanContext) -> list[MetricObservation]:
        return self.observations


def controlled_runner(analyzer: ControlledAnalyzer, context: ScanContext, timeout: int) -> RawAnalyzerResult:
    return RawAnalyzerResult(
        name=analyzer.name,
        available=True,
        version=f"{analyzer.name}-fixture",
    )


def test_typescript_fixture_materializes_expected_categories_and_samples(tmp_path: Path) -> None:
    expected = load_expected_fixture_data()["typescript"]
    destination = materialize_typescript_fixture(tmp_path / "typescript")

    assert not (destination / ".git").exists()
    assert not any(path.name == "__pycache__" for path in destination.rglob("*"))
    for relative_path, values in expected["files"].items():
        assert (destination / relative_path).is_file()
        assert classify(relative_path) == values["category"]
        assert detect_language(relative_path) == values["language"]

    source = (destination / expected["complex_function"]["path"]).read_text(encoding="utf-8")
    assert f"function {expected['complex_function']['qualified_name']}" in source
    assert source.count("    if (") >= expected["complex_function"]["minimum_cyclomatic_complexity"] - 1
    duplicate = expected["duplicate_functions"]
    assert all(f"function {name}" in source for name in duplicate["qualified_names"])
    body = (
        "    const result: number[] = [];\n"
        "    for (const value of values) {\n"
        "        if (value < 0) {\n"
        "            result.push(0);\n"
        "        } else {\n"
        "            result.push(value);\n"
        "        }\n"
        "    }"
    )
    assert source.count(body) == 2
    assert len(body.splitlines()) >= duplicate["minimum_matching_body_lines"]


def test_typescript_fixture_preserves_scan_report_and_sarif_contracts(tmp_path: Path) -> None:
    destination = materialize_typescript_fixture(tmp_path / "typescript")
    paths = [
        "src/calculations.ts", "src/stable value.ts", "tests/calculations.test.ts",
        "generated/client.ts", "vendor/dependency.ts", "config/settings.json",
    ]
    file_observations = [MetricObservation(
        "file", path, {"language": detect_language(path), "loc": nloc + 10, "nloc": nloc},
    ) for path, nloc in zip(paths, (700, 20, 900, 900, 900, 10), strict=True)]
    analyzers = [
        ControlledAnalyzer("scc", file_observations),
        ControlledAnalyzer("lizard", [
            MetricObservation(
                "function", "src/calculations.ts", {
                    "qualified_name": "complexDecision", "start_line": 2, "end_line": 38,
                    "nloc": 37, "cyclomatic_complexity": 13,
                },
            ),
            MetricObservation(
                "function", "src/stable value.ts", {
                    "qualified_name": "stableValue", "start_line": 1, "end_line": 3,
                    "nloc": 51, "cyclomatic_complexity": 1,
                },
            ),
        ]),
        ControlledAnalyzer("jscpd", [MetricObservation(
            "duplication", "src/calculations.ts", {"duplicated_lines": 100},
        )]),
    ]
    config = {
        "project": {"name": "small-typescript-project"},
        "thresholds": {
            "file_nloc_review": 300,
            "file_nloc_high": 500,
            "function_nloc_review": 50,
            "cyclomatic_complexity_review": 10,
            "duplication_ratio_review": 0.10,
        },
    }

    first = scan_repository(
        destination, config=config, config_hash="typescript-fixture-config",
        analyzers=analyzers, runner=controlled_runner,
    )
    second = scan_repository(
        destination, config=config, config_hash="typescript-fixture-config",
        analyzers=analyzers, runner=controlled_runner,
    )

    assert isinstance(first, ReportDocument)
    assert first.schema_version == 1
    assert {metric.path for metric in first.files} == set(paths)
    assert {metric.path for metric in first.files if metric.category == "production"} == {
        "src/calculations.ts", "src/stable value.ts",
    }
    assert {risk.path for risk in first.risks} == {"src/calculations.ts", "src/stable value.ts"}
    assert {finding.path for finding in first.findings} == {
        "src/calculations.ts", "src/stable value.ts",
    }
    assert all(metric.provenance.parse_complete for metric in first.files)
    assert render_json(first) == render_json(second)
    assert render_sarif(first) == render_sarif(second)

    sarif = json.loads(render_sarif(first))
    run = sarif["runs"][0]
    assert run["results"]
    assert any(
        result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        == "src/stable%20value.ts"
        for result in run["results"]
    )
    assert any(
        result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        == "src/calculations.ts"
        for result in run["results"]
    )
    assert sarif["version"] == "2.1.0"
    assert run["properties"]["commit"] == first.commit

    stored = read_json_report(destination / ".code-health" / "reports" / "report.json")
    cli = CliRunner()
    sarif_result = cli.invoke(app, ["report", "--format", "sarif", str(destination)])
    markdown_result = cli.invoke(app, ["report", str(destination)])
    assert sarif_result.exit_code == 0
    assert markdown_result.exit_code == 0
    assert sarif_result.output == render_sarif(stored)
    assert markdown_result.output == render_markdown(stored)
