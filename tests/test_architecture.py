from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_architect_optimizer.architecture import analyze_python_dependencies
from code_architect_optimizer.reports import render_json, render_markdown, render_sarif
from code_architect_optimizer.scan import scan_repository
from tests.test_scan import FakeAnalyzer, fake_runner


def _not_excluded(path: str) -> bool:
    return path.startswith((".git/", ".code-health/"))


def test_architecture_resolves_local_imports_and_canonicalizes_cycles(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from c import value\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("from a import thing\nvalue = thing\n", encoding="utf-8")
    result = analyze_python_dependencies(tmp_path, excluded=_not_excluded)

    assert result.dependencies == {"a.py": {"b.py"}, "b.py": {"c.py"}, "c.py": {"a.py"}}
    assert result.cycles == [("a.py", "b.py", "c.py")]


def test_architecture_scan_is_disabled_by_default_and_populates_metrics_when_enabled(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value = 1\n", encoding="utf-8")

    disabled = scan_repository(tmp_path, config={"project": {"name": "disabled"}}, write_reports=False)
    assert all(metric.fan_in == metric.fan_out == 0 for metric in disabled.files)
    assert not any(finding.rule_id == "architecture.import-cycle" for finding in disabled.findings)

    enabled = scan_repository(
        tmp_path,
        config={"project": {"name": "enabled"}, "architecture": {"enabled": True}},
        write_reports=False,
    )
    metrics = {metric.path: metric for metric in enabled.files}
    assert metrics["a.py"].fan_out == 1
    assert metrics["b.py"].fan_in == 1
    assert any(item.kind == "architecture-dependency" for item in enabled.evidence)


def test_architecture_does_not_guess_ambiguous_or_malformed_imports(tmp_path: Path) -> None:
    (tmp_path / "one.py").write_text("from shared import value\n", encoding="utf-8")
    (tmp_path / "first" ).mkdir()
    (tmp_path / "second" ).mkdir()
    (tmp_path / "first" / "shared.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "second" / "shared.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    result = analyze_python_dependencies(tmp_path, excluded=_not_excluded)

    assert result.dependencies["one.py"] == set()
    assert result.unresolved_imports >= 1


@pytest.mark.parametrize(("statement", "target"), [
    ("from shared import value", "shared.py"),
    ("from .shared import value", "pkg/shared.py"),
    ("from ..shared import value", "shared.py"),
    ("from pkg import shared", "pkg/shared.py"),
    ("from . import shared", "pkg/shared.py"),
])
def test_from_imports_distinguish_absolute_relative_and_package_children(
    tmp_path: Path, statement: str, target: str,
) -> None:
    (tmp_path / "shared.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg/shared.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "pkg/entry.py").write_text(statement + "\n", encoding="utf-8")
    result = analyze_python_dependencies(tmp_path, excluded=_not_excluded)
    if statement.startswith("from .."):
        assert result.dependencies["pkg/entry.py"] == set()
        assert result.unresolved_imports == 1
    else:
        assert result.dependencies["pkg/entry.py"] == {target}


def test_relative_parent_and_package_attributes(tmp_path: Path) -> None:
    (tmp_path / "pkg/sub").mkdir(parents=True)
    (tmp_path / "pkg/__init__.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "pkg/sub/__init__.py").write_text("from .. import value\n", encoding="utf-8")
    (tmp_path / "pkg/entry.py").write_text("from pkg import value\n", encoding="utf-8")
    result = analyze_python_dependencies(tmp_path, excluded=_not_excluded)
    assert result.dependencies["pkg/entry.py"] == {"pkg/__init__.py"}
    assert result.dependencies["pkg/sub/__init__.py"] == {"pkg/__init__.py"}
    assert result.unresolved_imports == 0


def test_ambiguous_child_never_falls_back_to_package(tmp_path: Path) -> None:
    (tmp_path / "pkg/child").mkdir(parents=True)
    (tmp_path / "pkg/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg/child.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "pkg/child/__init__.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "entry.py").write_text("from pkg import child\n", encoding="utf-8")
    result = analyze_python_dependencies(tmp_path, excluded=_not_excluded)
    assert result.dependencies["entry.py"] == set()
    assert result.unresolved_imports == 1


def test_cycle_groups_are_stable_without_inventing_sorted_edges(tmp_path: Path) -> None:
    for name, target in (("c", "b"), ("b", "a"), ("a", "c")):
        (tmp_path / f"{name}.py").write_text(f"import {target}\n", encoding="utf-8")
    config = {"project": {"name": "cycle"}, "architecture": {"enabled": True}}
    first = scan_repository(
        tmp_path, config=config, analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    second = scan_repository(
        tmp_path, config=config, analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)
    assert render_sarif(first) == render_sarif(second)
    finding = first.findings[0]
    assert finding.rule_id == "architecture.import-cycle"
    assert finding.path == "a.py" and finding.actual == 3
    assert " -> " not in finding.message
    assert all(name in finding.message for name in ("a.py", "b.py", "c.py"))
    metrics = {item.path: item for item in first.files}
    assert all(item.fan_in == item.fan_out == 1 for item in metrics.values())
    assert all(item.risk_score == 0 for item in first.risks)
    run = json.loads(render_sarif(first))["runs"][0]
    assert run["results"][0]["ruleId"] == "architecture.import-cycle"
    assert run["properties"]["parse_incomplete"] is False
    assert all(item.provenance.config_hash == first.config_hash for item in first.evidence)


def test_architecture_exclusions_and_nonproduction_cycle_governance(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/a.py").write_text("import tests.b\n", encoding="utf-8")
    (tmp_path / "tests/b.py").write_text("import tests.a\n", encoding="utf-8")
    (tmp_path / "excluded.py").write_text("import excluded\n", encoding="utf-8")
    report = scan_repository(
        tmp_path,
        config={"architecture": {"enabled": True}, "scan": {"exclude": ["excluded.py"]}},
        analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    assert {item.path for item in report.files} == {"tests/a.py", "tests/b.py"}
    assert report.findings == [] and report.risks == []
    assert any(item.kind == "architecture-dependency" for item in report.evidence)


def test_unresolved_dynamic_and_malformed_inputs_mark_coverage_incomplete(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text(
        "import external\n__import__('runtime')\n", encoding="utf-8",
    )
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    report = scan_repository(
        tmp_path, config={"architecture": {"enabled": True}},
        analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    status = [item for item in report.evidence if item.kind == "architecture-status"]
    assert status and status[0].raw_value >= 3
    assert status[0].provenance.parse_complete is False
    assert json.loads(render_sarif(report))["runs"][0]["properties"]["parse_incomplete"] is True


def test_self_import_and_deep_graph_do_not_crash_cycle_detection(tmp_path: Path) -> None:
    for index in range(1050):
        target = (index + 1) % 1050
        (tmp_path / f"module{index}.py").write_text(f"import module{target}\n", encoding="utf-8")
    (tmp_path / "self_import.py").write_text("import self_import\n", encoding="utf-8")
    result = analyze_python_dependencies(tmp_path, excluded=_not_excluded)
    assert len(result.cycles) == 2
    assert ("self_import.py",) in result.cycles
    assert len(next(cycle for cycle in result.cycles if len(cycle) > 1)) == 1050


def _boundary_config() -> dict:
    return {
        "project": {"name": "boundary"},
        "architecture": {
            "enabled": True,
            "boundaries": {
                "enabled": True,
                "layers": {
                    "api": ["api/**"],
                    "domain": ["domain/**"],
                    "internal": ["internal/**"],
                },
                "allowed": {"api": ["domain"], "internal": ["domain"]},
            },
        },
    }


def test_boundary_policy_emits_allowed_and_forbidden_evidence_without_new_schema_fields(
    tmp_path: Path,
) -> None:
    (tmp_path / "api").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "internal").mkdir()
    (tmp_path / "api/entry.py").write_text(
        "from domain import model\nfrom internal import helper\nimport external\n",
        encoding="utf-8",
    )
    (tmp_path / "domain/model.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "internal/helper.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/entry.py").write_text("from internal import helper\n", encoding="utf-8")
    (tmp_path / "misc").mkdir()
    (tmp_path / "misc/entry.py").write_text("from domain import model\n", encoding="utf-8")

    first = scan_repository(
        tmp_path, config=_boundary_config(), analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    second = scan_repository(
        tmp_path, config=_boundary_config(), analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)
    assert render_sarif(first) == render_sarif(second)
    assert [item.rule_id for item in first.findings] == ["architecture.boundary-forbidden"]
    assert first.findings[0].path == "api/entry.py"
    assert "internal/helper.py" in first.findings[0].message
    decisions = {
        (item.path, item.raw_value)
        for item in first.evidence
        if item.kind == "architecture-boundary" and item.metric == "decision"
    }
    assert ("api/entry.py", "allowed") in decisions
    assert ("api/entry.py", "forbidden") in decisions
    assert ("tests/entry.py", "unclassified") in decisions
    assert ("misc/entry.py", "unclassified") in decisions
    assert all(metric.risk_score == 0 for metric in first.risks)
    data = json.loads(render_json(first))
    assert data["schema_version"] == 1
    sarif = json.loads(render_sarif(first))
    assert sarif["runs"][0]["results"][0]["ruleId"] == "architecture.boundary-forbidden"
    assert sarif["runs"][0]["properties"]["parse_incomplete"] is True


def test_boundary_policy_rejects_invalid_configuration_and_reports_ambiguous_coverage(
    tmp_path: Path,
) -> None:
    (tmp_path / "api").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "api/entry.py").write_text("from domain import model\n", encoding="utf-8")
    (tmp_path / "domain/model.py").write_text("value = 1\n", encoding="utf-8")
    ambiguous = _boundary_config()
    ambiguous["architecture"]["boundaries"]["layers"]["public"] = ["api/**"]
    report = scan_repository(
        tmp_path, config=ambiguous, analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    assert report.findings == []
    status = [item for item in report.evidence if item.kind == "architecture-boundary-status"]
    assert status and status[0].provenance.parse_complete is False

    invalid = _boundary_config()
    invalid["architecture"]["boundaries"]["allowed"] = {"api": ["missing"]}
    invalid_report = scan_repository(
        tmp_path, config=invalid, analyzers=[FakeAnalyzer("empty")], runner=fake_runner,
    )
    invalid_status = [
        item for item in invalid_report.evidence
        if item.kind == "architecture-boundary-status" and item.raw_value == "invalid"
    ]
    assert invalid_status and invalid_status[0].provenance.parse_complete is False
