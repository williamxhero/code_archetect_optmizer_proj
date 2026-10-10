"""Baseline store + compare + ratchet (Phase 1).

baseline.json: schema_version / repository / commit / created_at / rules / known_findings.
CI modes: report (never fails) / ratchet (new-or-worsened fails) / strict (any finding fails).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from code_architect_optimizer.domain.models import Finding

BASELINE_SCHEMA_VERSION = 1


def baseline_path(work_dir: str) -> str:
    return os.path.join(work_dir, "baseline.json")


def finding_key(f: Finding) -> str:
    return f"{f.rule_id}::{f.path}::{f.line}"


def save_baseline(work_dir: str, repository: str, commit: str,
                  rules: dict[str, Any], findings: list[Finding]) -> str:
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "repository": repository,
        "commit": commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rules": rules,
        "known_findings": {finding_key(f): {"severity": f.severity, "actual": f.actual}
                           for f in findings},
    }
    path = baseline_path(work_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def load_baseline(path: str) -> dict[str, Any] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 - corrupt baseline reads as absent
        return None


def compare(findings: list[Finding], baseline: dict[str, Any] | None) -> dict[str, Any]:
    """Return {new, worsened, fixed, unchanged} finding lists (as dicts)."""
    if baseline is None:
        return {"new": [f.model_dump() for f in findings], "worsened": [],
                "fixed": [], "unchanged": []}
    known = baseline.get("known_findings") or {}
    current = {finding_key(f): f for f in findings}
    new, worsened, unchanged = [], [], []
    for key, f in current.items():
        if key not in known:
            new.append(f.model_dump())
        else:
            old = known[key] or {}
            try:
                if float(f.actual) > float(old.get("actual", 0)):
                    worsened.append(f.model_dump())
                else:
                    unchanged.append(f.model_dump())
            except (ValueError, TypeError):
                unchanged.append(f.model_dump())
    fixed = [{"key": k, **(v if isinstance(v, dict) else {})} for k, v in known.items()
             if k not in current]
    return {"new": new, "worsened": worsened, "fixed": fixed, "unchanged": unchanged}


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
    return True, f"unknown mode {mode!r}, passing open-loop"
