"""Rule-based risk scoring (Phase 1).

Structural risk and change pressure are computed separately; final priority
= structure x pressure x business factor. A complex-but-stable file must NOT
outrank a moderately-complex-but-churning one.
"""

from __future__ import annotations

from typing import Any

from code_architect_optimizer.domain.models import FileMetric, Finding, FunctionMetric, RiskScore


def score_file(
    f: FileMetric,
    functions: list[FunctionMetric],
    thresholds: dict[str, Any],
    business_factor: float = 1.0,
) -> tuple[RiskScore, list[Finding]]:
    t_file = float(thresholds.get("file_nloc_review", 300))
    t_high = float(thresholds.get("file_nloc_high", 500))
    t_fn = float(thresholds.get("function_nloc_review", 50))
    t_cc = float(thresholds.get("cyclomatic_complexity_review", 10))
    t_dup = float(thresholds.get("duplication_ratio_review", 0.10))

    structure = 0.0
    pressure = 0.0
    reasons: list[str] = []
    findings: list[Finding] = []

    def add_finding(rule_id: str, severity: str, line: int, metric: str,
                    actual: float, threshold: float, source: str, message: str) -> None:
        findings.append(Finding(rule_id=rule_id, severity=severity, path=f.path,  # type: ignore[arg-type]
                                line=line, metric=metric, actual=actual,
                                threshold=threshold, evidence_source=source, message=message))

    if f.nloc > t_file:
        structure += 1
        reasons.append(f"nloc {f.nloc} > review {t_file:g}")
        add_finding("file.nloc.review", "medium", 0, "nloc", f.nloc, t_file,
                    f.provenance.source_tool, "文件行数超过模块化审查触发线")
    if f.nloc > t_high:
        structure += 2
        reasons.append(f"nloc {f.nloc} > high {t_high:g}")
        add_finding("file.nloc.high", "high", 0, "nloc", f.nloc, t_high,
                    f.provenance.source_tool, "文件行数超过高线，强烈建议审查")
    if f.duplication_ratio > t_dup:
        structure += 1
        reasons.append(f"duplication {f.duplication_ratio:.0%} > {t_dup:.0%}")
        add_finding("file.duplication.high", "medium", 0, "duplication_ratio",
                    f.duplication_ratio, t_dup, "jscpd", "重复代码比例超过阈值")

    for fn in functions:
        if fn.cyclomatic_complexity > t_cc:
            structure += 2
            reasons.append(f"{fn.qualified_name} CC {fn.cyclomatic_complexity} > {t_cc:g}")
            add_finding("function.complexity.high", "high", fn.start_line,
                        "cyclomatic_complexity", fn.cyclomatic_complexity, t_cc,
                        fn.provenance.source_tool, f"函数圈复杂度超过审查阈值（{fn.qualified_name}）")
        if fn.nloc > t_fn:
            structure += 1
            reasons.append(f"{fn.qualified_name} nloc {fn.nloc} > {t_fn:g}")
            add_finding("function.nloc.high", "medium", fn.start_line, "nloc",
                        fn.nloc, t_fn, fn.provenance.source_tool,
                        f"函数行数超过审查阈值（{fn.qualified_name}）")

    if f.churn_90d >= 10:
        pressure += 2
        reasons.append(f"churn {f.churn_90d} (>=10 in 90d)")
    elif f.churn_90d >= 3:
        pressure += 1
        reasons.append(f"churn {f.churn_90d} (>=3 in 90d)")
    if f.contributors_90d >= 3:
        pressure += 1
        reasons.append(f"{f.contributors_90d} contributors in 90d")

    priority = structure * max(pressure, 0.5) * business_factor
    return RiskScore(path=f.path, risk_score=structure, change_pressure=pressure,
                     refactor_priority=round(priority, 2), reasons=reasons), findings
