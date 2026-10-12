"""scc adapter: file-level size metrics (loc/nloc per language)."""

from __future__ import annotations

import json
import subprocess

from code_architect_optimizer.analyzers.base import (
    Analyzer,
    MetricObservation,
    RawAnalyzerResult,
    which,
)
from code_architect_optimizer.domain.models import ScanContext


class SccAnalyzer:
    name = "scc"

    def is_available(self) -> bool:
        return which("scc") is not None

    def tool_version(self) -> str:
        try:
            p = subprocess.run(["scc", "--version"], capture_output=True, text=True, timeout=30)
            return (p.stdout or p.stderr or "").strip().splitlines()[0][:80]
        except Exception:  # noqa: BLE001
            return "unknown"

    def build_command(self, context: ScanContext) -> list[str]:
        return ["scc", "--by-file", "--format", "json", "."]

    def parse(self, result: RawAnalyzerResult, context: ScanContext) -> list[MetricObservation]:
        obs: list[MetricObservation] = []
        if not result.available or result.error:
            return obs
        try:
            payload = json.loads(result.stdout or "[]")
        except Exception:  # noqa: BLE001 - keep raw, emit nothing
            return obs
        for entry in payload if isinstance(payload, list) else []:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("Location") or entry.get("Filename") or "")
            if not path:
                continue
            loc = int(entry.get("Lines") or 0)
            code = int(entry.get("Code") or 0)
            obs.append(MetricObservation(kind="file", path=path, data={
                "language": str(entry.get("Language") or "unknown"),
                "loc": loc,
                "nloc": code,
            }))
        return obs
