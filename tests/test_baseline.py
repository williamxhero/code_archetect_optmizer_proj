from __future__ import annotations

from code_architect_optimizer.baseline.compare import compare, gate
from code_architect_optimizer.baseline.store import load_baseline, save_baseline
from code_architect_optimizer.domain.models import Finding


def make_finding(path: str, actual: float, severity: str = "medium") -> Finding:
    return Finding(
        rule_id="file.nloc.review",
        severity=severity,
        path=path,
        line=0,
        metric="nloc",
        actual=actual,
        threshold=300,
        evidence_source="scc",
    )


def test_baseline_round_trip_and_comparison_states(tmp_path) -> None:
    baseline_findings = [
        make_finding("src/unchanged.py", 10),
        make_finding("src/worsened.py", 10, severity="high"),
        make_finding("src/fixed.py", 10),
    ]
    path = save_baseline(
        str(tmp_path),
        repository="example",
        commit="before",
        rules={"file_nloc_review": 300},
        findings=baseline_findings,
    )
    baseline = load_baseline(path)

    assert baseline is not None
    assert baseline["repository"] == "example"
    assert baseline["commit"] == "before"
    assert baseline["rules"] == {"file_nloc_review": 300}

    current = [
        make_finding("src/unchanged.py", 10),
        make_finding("src/worsened.py", 11, severity="high"),
        make_finding("src/new.py", 20, severity="critical"),
    ]
    comparison = compare(current, baseline)

    assert {finding["path"] for finding in comparison["new"]} == {"src/new.py"}
    assert {finding["path"] for finding in comparison["worsened"]} == {"src/worsened.py"}
    assert {finding["path"] for finding in comparison["unchanged"]} == {"src/unchanged.py"}
    assert [finding["key"] for finding in comparison["fixed"]] == [
        "file.nloc.review::src/fixed.py::0"
    ]


def test_baseline_comparison_without_existing_baseline_marks_all_findings_new() -> None:
    findings = [make_finding("src/new.py", 20)]

    comparison = compare(findings, None)

    assert comparison == {
        "new": [finding.model_dump() for finding in findings],
        "worsened": [],
        "fixed": [],
        "unchanged": [],
    }


def test_baseline_gates_cover_report_ratchet_and_strict_modes(tmp_path) -> None:
    finding = make_finding("src/new.py", 20, severity="high")
    comparison = compare([finding], None)

    assert gate("report", comparison, ["high"], [finding]) == (
        True,
        "report mode never fails",
    )
    assert gate("ratchet", comparison, ["high"], [finding]) == (
        False,
        "ratchet: 1 new/worsened finding(s) at ['high']",
    )
    assert gate("ratchet", comparison, ["critical"], [finding]) == (
        True,
        "ratchet: no new/worsened findings at gate severities",
    )
    assert gate("strict", comparison, ["high"], [finding]) == (
        False,
        "strict: 1 finding(s) at ['high']",
    )
    assert gate("strict", comparison, ["critical"], [finding]) == (
        True,
        "strict: no findings at gate severities",
    )
