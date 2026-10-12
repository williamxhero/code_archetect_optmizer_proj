"""Deterministic SARIF 2.1.0 export of a saved code-health report."""

from __future__ import annotations

import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote

from code_architect_optimizer.domain.schemas import ReportDocument

from ._common import stable_data

_LEVELS = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "note"}


def _artifact_uri(path: str) -> str:
    normalized = path.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if not normalized or normalized == "." or posix.is_absolute() or PureWindowsPath(path).drive or ".." in posix.parts:
        raise ValueError(f"SARIF requires a repository-relative file path: {path}")
    return quote(posix.as_posix(), safe="/")


def render_sarif(report: ReportDocument | dict[str, Any]) -> str:
    """Export findings without changing the frozen input schema or scan policy."""
    data = stable_data(report)
    rule_ids = sorted({finding["rule_id"] for finding in data["findings"]})
    rule_indexes = {rule_id: index for index, rule_id in enumerate(rule_ids)}
    results = []
    for finding in data["findings"]:
        results.append({
            "ruleId": finding["rule_id"],
            "ruleIndex": rule_indexes[finding["rule_id"]],
            "level": _LEVELS[finding["severity"]],
            "message": {"text": finding["message"] or (
                f"{finding['rule_id']}: {finding['metric'] or 'measured value'} "
                f"{finding['actual']:g} exceeds {finding['threshold']:g}."
            )},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": _artifact_uri(finding["path"])},
                "region": {"startLine": max(1, finding["line"])},
            }}],
            "properties": {
                "severity": finding["severity"],
                "metric": finding["metric"],
                "actual": finding["actual"],
                "threshold": finding["threshold"],
                "evidence_source": finding["evidence_source"],
                "original_line": finding["line"],
            },
        })
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "code-health",
                "informationUri": "https://github.com/williamxhero/code_archetect_optmizer_proj",
                "rules": [{"id": rule_id, "shortDescription": {"text": rule_id}} for rule_id in rule_ids],
            }},
            "results": results,
            "properties": {
                "repository": data["repository"],
                "commit": data["commit"],
                "config_hash": data["config_hash"],
                "tool_versions": data["tool_versions"],
                "unavailable_tools": data["unavailable_tools"],
                "parse_incomplete": any(
                    item.get("provenance") and not item["provenance"]["parse_complete"]
                    for collection in ("files", "functions", "evidence")
                    for item in data[collection]
                ),
            },
        }],
    }
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
