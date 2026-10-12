"""Public deterministic JSON and Markdown report seams."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from code_architect_optimizer.domain.schemas import ReportDocument

from .json import (
    JsonReportRenderer,
    read_json_report,
    render_json,
    render_json_report,
    write_json,
    write_json_report,
)
from .markdown import (
    MarkdownReportRenderer,
    render_markdown,
    render_markdown_report,
    write_markdown,
    write_markdown_report,
)

from .sarif import render_sarif

DEFAULT_REPORT_DIRECTORY = ".code-health/reports"


def write_report_artifacts(
    report: ReportDocument | dict[str, Any],
    repo_root: str | Path,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Write both standard report artifacts and return their paths.

    This is intentionally independent of the CLI.  Callers that already have
    a scan model can place both artifacts in the conventional
    ``.code-health/reports`` directory with one public call.
    """

    directory = Path(output_dir) if output_dir is not None else Path(repo_root) / DEFAULT_REPORT_DIRECTORY
    return {
        "json": write_json_report(report, directory),
        "markdown": write_markdown_report(report, directory),
    }


__all__ = [
    "DEFAULT_REPORT_DIRECTORY",
    "JsonReportRenderer",
    "MarkdownReportRenderer",
    "read_json_report",
    "render_json",
    "render_json_report",
    "render_markdown",
    "render_markdown_report",
    "render_sarif",
    "write_json",
    "write_json_report",
    "write_markdown",
    "write_markdown_report",
    "write_report_artifacts",
]
