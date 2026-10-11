"""Baseline store + compare + ratchet (Phase 1).

baseline.json: schema_version / repository / commit / created_at / rules / known_findings.
CI modes: report (never fails) / ratchet (new-or-worsened fails) / strict (any finding fails).
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from code_architect_optimizer.domain.models import Finding

BASELINE_SCHEMA_VERSION = 1
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}


class BaselineError(ValueError):
    """Raised when a baseline cannot be safely used for comparison."""


def baseline_path(work_dir: str) -> str:
    return os.path.join(work_dir, "baseline.json")


def finding_key(f: Finding) -> str:
    return f"{f.rule_id}::{f.path}::{f.line}"


def _baseline_payload(repository: str, commit: str, rules: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "repository": repository,
        "commit": commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rules": rules,
        "known_findings": {finding_key(f): {"severity": f.severity, "actual": f.actual}
                           for f in findings},
    }


def save_baseline(work_dir: str, repository: str, commit: str,
                  rules: dict[str, Any], findings: list[Finding]) -> str:
    path = baseline_path(work_dir)
    return save_baseline_file(path, repository, commit, rules, findings)


def save_baseline_file(path: str, repository: str, commit: str,
                       rules: dict[str, Any], findings: list[Finding]) -> str:
    payload = _baseline_payload(repository, commit, rules, findings)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    return path


def validate_baseline(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise BaselineError("baseline root must be a JSON object")
    if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise BaselineError(
            f"unsupported schema_version {payload.get('schema_version')!r}; expected {BASELINE_SCHEMA_VERSION}"
        )
    for field in ("repository", "commit", "created_at"):
        if not isinstance(payload.get(field), str):
            raise BaselineError(f"baseline field {field!r} must be a string")
    if not isinstance(payload.get("rules"), Mapping):
        raise BaselineError("baseline field 'rules' must be an object")
    known = payload.get("known_findings")
    if not isinstance(known, Mapping):
        raise BaselineError("baseline field 'known_findings' must be an object")
    for key, finding in known.items():
        if not isinstance(key, str) or not isinstance(finding, Mapping):
            raise BaselineError("baseline known_findings entries must be objects")
        if finding.get("severity") not in _VALID_SEVERITIES:
            raise BaselineError(f"baseline finding {key!r} has an invalid severity")
        try:
            actual = float(finding.get("actual"))
        except (TypeError, ValueError):
            raise BaselineError(f"baseline finding {key!r} has a non-numeric actual value") from None
        if not math.isfinite(actual):
            raise BaselineError(f"baseline finding {key!r} has a non-finite actual value")
    return dict(payload)


def load_baseline(path: str) -> dict[str, Any] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 - corrupt baseline reads as absent
        return None


def load_baseline_checked(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        raise BaselineError(f"baseline does not exist: {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"baseline is not valid JSON: {exc}") from None
    return validate_baseline(payload)


def _severity_rank(value: Any) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(value, 5)


def _finding_sort_key(finding: dict[str, Any]) -> tuple[Any, ...]:
    return (
        finding.get("path", ""),
        int(finding.get("line", 0) or 0),
        finding.get("rule_id", ""),
        finding.get("severity", ""),
        str(finding.get("actual", "")),
    )


def compare(findings: list[Finding], baseline: dict[str, Any] | None) -> dict[str, Any]:
    """Return {new, worsened, fixed, unchanged} finding lists (as dicts)."""
    if baseline is None:
        return {"new": sorted((f.model_dump() for f in findings), key=_finding_sort_key),
                "worsened": [], "fixed": [], "unchanged": []}
    known = baseline.get("known_findings") or {}
    current = {finding_key(f): f for f in findings}
    new, worsened, unchanged = [], [], []
    for key in sorted(current):
        f = current[key]
        if key not in known:
            new.append(f.model_dump())
            continue
        old = known[key] or {}
        try:
            actual_worsened = float(f.actual) > float(old.get("actual", 0))
        except (ValueError, TypeError):
            actual_worsened = False
        severity_worsened = _severity_rank(f.severity) < _severity_rank(old.get("severity"))
        if actual_worsened or severity_worsened:
            worsened.append(f.model_dump())
        else:
            unchanged.append(f.model_dump())
    fixed = [{"key": k, **(v if isinstance(v, dict) else {})} for k, v in sorted(known.items())
             if k not in current]
    return {
        "new": sorted(new, key=_finding_sort_key),
        "worsened": sorted(worsened, key=_finding_sort_key),
        "fixed": fixed,
        "unchanged": sorted(unchanged, key=_finding_sort_key),
    }


def gate(mode: str, comparison: dict[str, Any], fail_on: list[str],
         findings: list[Finding]) -> tuple[bool, str]:
    """Return (passed, reason). report always passes."""
    if mode == "report":
        return True, "report mode never fails"
    if mode == "ratchet":
        bad = [f for f in comparison["new"] + comparison["worsened"]
               if f.get("severity") in fail_on]
        if bad:
            return False, f"ratchet: {len(bad)} new/worsened finding(s) at {fail_on}"
        return True, "ratchet: no new/worsened findings at gate severities"
    if mode == "strict":
        bad = [f for f in findings if f.severity in fail_on]
        if bad:
            return False, f"strict: {len(bad)} finding(s) at {fail_on}"
        return True, "strict: no findings at gate severities"
    return False, f"unknown CI mode {mode!r}"
