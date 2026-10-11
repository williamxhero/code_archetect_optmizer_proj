"""jscpd adapter: duplication detection (JSON reporter)."""

from __future__ import annotations

import json
import os
import subprocess

from code_architect_optimizer.analyzers.base import (
    Analyzer,
    MetricObservation,
    RawAnalyzerResult,
    which,
)
from code_architect_optimizer.domain.models import ScanContext


class JscpdAnalyzer:
    name = "jscpd"

    def is_available(self) -> bool:
        return which("jscpd") is not None

    def tool_version(self) -> str:
        try:
            p = subprocess.run(["jscpd", "--version"], capture_output=True, text=True, timeout=30)
            return (p.stdout or p.stderr or "").strip().splitlines()[0][:80]
        except Exception:  # noqa: BLE001
            return "unknown"

    def build_command(self, context: ScanContext) -> list[str]:
        out = os.path.join(context.repo_root, context.work_dir, "raw", "jscpd.json")
        return ["jscpd", ".", "--reporters", "json", "--output",
                os.path.dirname(out), "--silent"]

    def parse(self, result: RawAnalyzerResult, context: ScanContext) -> list[MetricObservation]:
        obs: list[MetricObservation] = []
        report_path = os.path.join(context.repo_root, context.work_dir, "raw", "jscpd.json")
        if not os.path.isfile(report_path):
            return obs
        try:
            with open(report_path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:  # noqa: BLE001
            return obs
        dupes = payload.get("duplicates") or []
        per_file_lines: dict[str, int] = {}
        for d in dupes:
            try:
                lines = int(d.get("lines") or 0)
                for side in ("firstFile", "secondFile"):
                    f = d.get(side) or {}
                    name = str(f.get("name") or "")
                    if name:
                        per_file_lines[name] = per_file_lines.get(name, 0) + lines
            except (ValueError, AttributeError, TypeError):
                continue
        stats = payload.get("statistics") or {}
        total = stats.get("total") or {}
        for path, dup_lines in per_file_lines.items():
            rel = os.path.relpath(path, context.repo_root).replace(os.sep, "/") \
                if os.path.isabs(path) else path
            obs.append(MetricObservation(kind="duplication", path=rel, data={
                "duplicated_lines": dup_lines,
            }))
        _ = total
        return obs
