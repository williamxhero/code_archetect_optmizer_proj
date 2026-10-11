"""Deterministic Markdown report renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from code_architect_optimizer.domain.schemas import ReportDocument

from ._common import display, stable_data, validate_report

DEFAULT_MARKDOWN_NAME = "report.md"


def _row(values: list[Any]) -> str:
    return "| " + " | ".join(display(value) for value in values) + " |\n"


def render_markdown(report: ReportDocument | dict[str, Any]) -> str:
    """Render a report as stable Markdown without volatile timestamps."""

    data = stable_data(validate_report(report))
    lines = [
        "# Code Health Report\n",
        "\n",
        f"- Schema version: `{display(data['schema_version'])}`\n",
        f"- Repository: `{display(data['repository'])}`\n",
        f"- Commit: `{display(data['commit'])}`\n",
        f"- Config hash: `{display(data['config_hash'])}`\n",
    ]

    tools = data.get("tool_versions", {})
    if tools:
        lines.append("- Tools: " + ", ".join(f"`{display(name)}` {display(version)}" for name, version in tools.items()) + "\n")
    else:
        lines.append("- Tools: none\n")
    unavailable = data.get("unavailable_tools", [])
    lines.append("- Unavailable tools: " + (", ".join(f"`{display(tool)}`" for tool in unavailable) if unavailable else "none") + "\n")

    risks = data.get("risks", [])
    lines.extend(["\n## Risks\n\n", f"{len(risks)} risk(s), ordered by refactor priority.\n\n"])
    if risks:
        lines.extend([
            "| Priority | Risk score | Change pressure | Path | Reasons |\n",
            "| ---: | ---: | ---: | --- | --- |\n",
        ])
        for risk in risks:
            lines.append(_row([
                risk.get("refactor_priority", 0),
                risk.get("risk_score", 0),
                risk.get("change_pressure", 0),
                f"`{risk.get('path', '')}`",
                "; ".join(risk.get("reasons", [])),
            ]))
    else:
        lines.append("No risks reported.\n")

    findings = data.get("findings", [])
    lines.extend(["\n## Findings\n\n", f"{len(findings)} finding(s), ordered by severity and path.\n\n"])
    if findings:
        lines.extend([
            "| Severity | Path | Line | Rule | Metric | Actual | Threshold | Evidence |\n",
            "| --- | --- | ---: | --- | --- | ---: | ---: | --- |\n",
        ])
        for finding in findings:
            lines.append(_row([
                finding.get("severity", "info"),
                f"`{finding.get('path', '')}`",
                finding.get("line", 0),
                finding.get("rule_id", ""),
                finding.get("metric", ""),
                finding.get("actual", 0),
                finding.get("threshold", 0),
                f"{finding.get('evidence_source', 'unknown')}: {finding.get('message', '')}",
            ]))
    else:
        lines.append("No findings reported.\n")

    files = data.get("files", [])
    lines.extend(["\n## Files\n\n"])
    if files:
        lines.extend([
            "| Path | Category | Language | NLOC | Complexity | Duplication | Churn (90d) |\n",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |\n",
        ])
        for file_metric in files:
            lines.append(_row([
                f"`{file_metric.get('path', '')}`",
                file_metric.get("category", "unknown"),
                file_metric.get("language", "unknown"),
                file_metric.get("nloc", 0),
                file_metric.get("complexity", 0),
                file_metric.get("duplication_ratio", 0),
                file_metric.get("churn_90d", 0),
            ]))
    else:
        lines.append("No file metrics reported.\n")

    functions = data.get("functions", [])
    lines.extend(["\n## Functions\n\n"])
    if functions:
        lines.extend([
            "| File | Function | Lines | NLOC | Cyclomatic complexity |\n",
            "| --- | --- | ---: | ---: | ---: |\n",
        ])
        for function in functions:
            lines.append(_row([
                f"`{function.get('file_path', '')}`",
                function.get("qualified_name", ""),
                f"{function.get('start_line', 0)}-{function.get('end_line', 0)}",
                function.get("nloc", 0),
                function.get("cyclomatic_complexity", 0),
            ]))
    else:
        lines.append("No function metrics reported.\n")

    evidence = data.get("evidence", [])
    lines.extend(["\n## Evidence\n\n"])
    if evidence:
        lines.extend([
            "| Source | Tool version | Kind | Path | Metric | Raw value | Excerpt |\n",
            "| --- | --- | --- | --- | --- | --- | --- |\n",
        ])
        for item in evidence:
            lines.append(_row([
                item.get("source_tool", "unknown"),
                item.get("tool_version", "unknown"),
                item.get("kind", "metric"),
                f"`{item.get('path', '')}`" if item.get("path") else "",
                item.get("metric", ""),
                item.get("raw_value"),
                item.get("excerpt", ""),
            ]))
    else:
        lines.append("No additional evidence reported; metric provenance is embedded above.\n")

    return "".join(lines)


render_markdown_report = render_markdown


def _artifact_path(destination: str | Path, default_name: str) -> Path:
    path = Path(destination)
    if path.exists() and path.is_dir():
        return path / default_name
    if not path.suffix:
        return path / default_name
    return path


def write_markdown_report(
    report: ReportDocument | dict[str, Any],
    destination: str | Path,
) -> Path:
    """Write Markdown and return its path."""

    path = _artifact_path(destination, DEFAULT_MARKDOWN_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return path


write_markdown = write_markdown_report


class MarkdownReportRenderer:
    """Small public seam for integrations that want an object renderer."""

    def render(self, report: ReportDocument | dict[str, Any]) -> str:
        return render_markdown(report)

    def write(self, report: ReportDocument | dict[str, Any], destination: str | Path) -> Path:
        return write_markdown_report(report, destination)
