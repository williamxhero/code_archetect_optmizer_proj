from __future__ import annotations

import pytest

from code_architect_optimizer.domain.models import FileMetric, FunctionMetric, Provenance, RiskScore
from code_architect_optimizer.risk.prioritization import prioritize
from code_architect_optimizer.risk.scoring import score_file


THRESHOLDS = {
    "file_nloc_review": 300,
    "file_nloc_high": 500,
    "function_nloc_review": 50,
    "cyclomatic_complexity_review": 10,
    "duplication_ratio_review": 0.10,
}


def test_score_file_separates_structure_pressure_and_priority() -> None:
    metric = FileMetric(
        path="src/hot.py",
        nloc=501,
        duplication_ratio=0.11,
        churn_90d=10,
        contributors_90d=3,
        provenance=Provenance(source_tool="scc"),
    )
    function = FunctionMetric(
        file_path=metric.path,
        qualified_name="hot",
        start_line=24,
        nloc=51,
        cyclomatic_complexity=11,
        provenance=Provenance(source_tool="lizard"),
    )

    risk, findings = score_file(metric, [function], THRESHOLDS, business_factor=1.5)

    assert risk.risk_score == 7
    assert risk.change_pressure == 3
    assert risk.refactor_priority == 31.5
    assert {finding.rule_id for finding in findings} == {
        "file.nloc.review",
        "file.nloc.high",
        "file.duplication.high",
        "function.complexity.high",
        "function.nloc.high",
    }
    assert all(finding.path == metric.path for finding in findings)


@pytest.mark.parametrize(
    ("metric", "function", "expected_risk", "expected_rules"),
    [
        (
            FileMetric(path="src/boundary.py", nloc=300, duplication_ratio=0.10),
            FunctionMetric(file_path="src/boundary.py", qualified_name="boundary", nloc=50, cyclomatic_complexity=10),
            0,
            set(),
        ),
        (
            FileMetric(path="src/boundary.py", nloc=500, duplication_ratio=0.10),
            FunctionMetric(file_path="src/boundary.py", qualified_name="boundary", nloc=50, cyclomatic_complexity=10),
            1,
            {"file.nloc.review"},
        ),
    ],
)
def test_structure_thresholds_are_strictly_greater(
    metric: FileMetric,
    function: FunctionMetric,
    expected_risk: int,
    expected_rules: set[str],
) -> None:
    risk, findings = score_file(metric, [function], THRESHOLDS)

    assert risk.risk_score == expected_risk
    assert {finding.rule_id for finding in findings} == expected_rules


def test_change_pressure_thresholds_are_inclusive() -> None:
    metric = FileMetric(path="src/churn.py", churn_90d=10, contributors_90d=3)

    risk, findings = score_file(metric, [], THRESHOLDS)

    assert risk.risk_score == 0
    assert risk.change_pressure == 3
    assert risk.refactor_priority == 0
    assert findings == []


def test_prioritize_keeps_churning_moderate_risk_ahead_of_stable_complexity() -> None:
    stable, _ = score_file(
        FileMetric(path="src/stable.py", nloc=501, churn_90d=0),
        [FunctionMetric(file_path="src/stable.py", qualified_name="complex", cyclomatic_complexity=11)],
        THRESHOLDS,
    )
    churning, _ = score_file(
        FileMetric(path="src/churning.py", nloc=301, churn_90d=10, contributors_90d=3),
        [FunctionMetric(file_path="src/churning.py", qualified_name="active", cyclomatic_complexity=11)],
        THRESHOLDS,
    )

    ranked = prioritize([stable, churning])

    assert ranked == [churning, stable]
    assert churning.refactor_priority > stable.refactor_priority


def test_prioritize_applies_top_limit_and_deterministic_tie_breaking() -> None:
    risks = [
        RiskScore(path="z.py", risk_score=2, refactor_priority=4),
        RiskScore(path="a.py", risk_score=2, refactor_priority=4),
        RiskScore(path="b.py", risk_score=1, refactor_priority=4),
    ]

    assert [risk.path for risk in prioritize(risks, top=2)] == ["a.py", "z.py"]
