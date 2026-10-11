"""Shared validation, redaction, and ordering for report renderers."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import Any

from code_architect_optimizer.domain.schemas import ReportDocument

_REDACTED = "[REDACTED]"
_DROP = object()
_MAX_STRING_LENGTH = 2_000
_MAX_EXCERPT_LENGTH = 500
_SECRET_KEY = re.compile(
    r"(?i)(token|password|secret|api[_-]?key|apikey|authorization)"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(token|password|secret|api[_-]?key|apikey|authorization)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIALS = re.compile(r"(?i)(://[^/:\s]+:)[^@/\s]+@")
_RAW_OUTPUT_KEYS = {
    "stderr",
    "stdout",
    "raw",
    "raw_output",
    "raw_stderr",
    "raw_stdout",
    "analyzer_stderr",
    "analyzer_stdout",
    "environment",
    "env",
    "environ",
}

# Only values from variables whose names identify credentials are considered.
# Ordinary process configuration is never copied into a report in the first
# place; this second layer prevents an accidentally supplied credential from
# appearing in an evidence excerpt or message.
def _secret_env_values() -> frozenset[str]:
    return frozenset(
        value
        for key, value in os.environ.items()
        if _SECRET_KEY.search(key) and len(value) >= 4
    )


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def validate_report(report: ReportDocument | Mapping[str, Any]) -> ReportDocument:
    """Validate a renderer input without relying on CLI implementation details."""

    if isinstance(report, ReportDocument):
        return report
    return ReportDocument.model_validate(report)


def _redact_string(value: str) -> str:
    for secret in _secret_env_values():
        value = value.replace(secret, _REDACTED)
    value = _BEARER.sub("Bearer " + _REDACTED, value)
    value = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}={_REDACTED}", value)
    value = _URL_CREDENTIALS.sub(r"\1" + _REDACTED + "@", value)
    return value


def _sanitize(value: Any, key: str | None = None) -> Any:
    normalized_key = key.lower().replace("-", "_") if key else ""
    if normalized_key in _RAW_OUTPUT_KEYS:
        return _DROP
    if _SECRET_KEY.search(normalized_key):
        return _REDACTED
    if isinstance(value, str):
        limit = _MAX_EXCERPT_LENGTH if normalized_key == "excerpt" else _MAX_STRING_LENGTH
        return _redact_string(value)[:limit]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for child_key, child_value in value.items():
            sanitized = _sanitize(child_value, str(child_key))
            if sanitized is not _DROP:
                result[str(child_key)] = sanitized
        return result
    if isinstance(value, list):
        result = []
        for child_value in value:
            sanitized = _sanitize(child_value)
            if sanitized is not _DROP:
                result.append(sanitized)
        return result
    return value


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _stable_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def stable_data(report: ReportDocument | Mapping[str, Any]) -> dict[str, Any]:
    """Return a sanitized and canonically ordered report representation.

    ``scanned_at`` is intentionally blanked in the rendered representation.
    Analyzer timestamps are useful while debugging raw data, but are volatile
    and must not make a report differ when the commit and configuration do not.
    """

    document = validate_report(report)
    data = _sanitize(document.model_dump(mode="json"))
    if not isinstance(data, dict):  # pragma: no cover - model_dump is a dict
        raise TypeError("report model did not produce an object")

    data["scanned_at"] = ""
    for collection in ("files", "functions", "evidence"):
        for item in data.get(collection, []):
            provenance = item.get("provenance") if isinstance(item, dict) else None
            if isinstance(provenance, dict):
                provenance["scanned_at"] = ""

    data["tool_versions"] = dict(sorted(data.get("tool_versions", {}).items()))
    data["unavailable_tools"] = sorted(data.get("unavailable_tools", []))
    data["files"] = sorted(data.get("files", []), key=lambda item: (item.get("path", ""), _stable_key(item)))
    data["functions"] = sorted(
        data.get("functions", []),
        key=lambda item: (
            item.get("file_path", ""),
            int(item.get("start_line", 0)),
            item.get("qualified_name", ""),
            int(item.get("end_line", 0)),
            _stable_key(item),
        ),
    )
    data["findings"] = sorted(
        data.get("findings", []),
        key=lambda item: (
            _SEVERITY_RANK.get(item.get("severity", "info"), len(_SEVERITY_RANK)),
            item.get("path", ""),
            int(item.get("line", 0)),
            item.get("rule_id", ""),
            item.get("metric", ""),
            item.get("message", ""),
            _stable_key(item),
        ),
    )
    for risk in data.get("risks", []):
        risk["reasons"] = sorted(risk.get("reasons", []))
    data["risks"] = sorted(
        data.get("risks", []),
        key=lambda item: (
            -_number(item.get("refactor_priority")),
            -_number(item.get("risk_score")),
            -_number(item.get("change_pressure")),
            item.get("path", ""),
            _stable_key(item),
        ),
    )
    data["evidence"] = sorted(
        data.get("evidence", []),
        key=lambda item: (
            item.get("path", ""),
            item.get("metric", ""),
            item.get("kind", ""),
            item.get("source_tool", ""),
            _stable_key(item.get("raw_value")),
            _stable_key(item),
        ),
    )
    return data


def display(value: Any) -> str:
    """Convert an already sanitized value into one-line Markdown text."""

    if value is None:
        return ""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        text = str(value)
    return text.replace("\r", " ").replace("\n", " ").replace("|", "\\|")
