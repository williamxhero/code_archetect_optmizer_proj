"""Deterministic, schema-validated JSON report renderer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_architect_optimizer.domain.schemas import ReportDocument

from ._common import stable_data, validate_report

DEFAULT_JSON_NAME = "report.json"


def render_json(report: ReportDocument | dict[str, Any]) -> str:
    """Render a report as stable UTF-8 JSON terminated by one newline.

    The input is validated against :class:`ReportDocument`; list ordering,
    credential redaction, and volatile timestamps are normalized before
    serialization.  ``sort_keys`` makes nested maps deterministic as well.
    """

    payload = stable_data(validate_report(report))
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


# Descriptive alias for callers that prefer the artifact format in the name.
render_json_report = render_json


def _artifact_path(destination: str | Path, default_name: str) -> Path:
    path = Path(destination)
    if path.exists() and path.is_dir():
        return path / default_name
    if not path.suffix:
        return path / default_name
    return path


def write_json_report(
    report: ReportDocument | dict[str, Any],
    destination: str | Path,
) -> Path:
    """Write a JSON report and return its path.

    Passing ``.code-health/reports`` (or another existing directory) writes
    ``report.json`` inside it; passing a filename writes exactly that file.
    """

    path = _artifact_path(destination, DEFAULT_JSON_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(report), encoding="utf-8", newline="\n")
    return path


write_json = write_json_report


def read_json_report(source: str | Path) -> ReportDocument:
    """Read and validate a previously rendered JSON report."""

    path = Path(source)
    return ReportDocument.model_validate_json(path.read_text(encoding="utf-8"))


class JsonReportRenderer:
    """Small public seam for integrations that want an object renderer."""

    def render(self, report: ReportDocument | dict[str, Any]) -> str:
        return render_json(report)

    def write(self, report: ReportDocument | dict[str, Any], destination: str | Path) -> Path:
        return write_json_report(report, destination)
