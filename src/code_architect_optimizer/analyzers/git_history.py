"""Native git history analysis: churn + contributors over trailing 90 days.

No Code Maat dependency in Phase 1; plain `git log` parsing.
"""

from __future__ import annotations

import datetime as _dt
import subprocess

from code_architect_optimizer.analyzers.base import (
    Analyzer,
    MetricObservation,
    RawAnalyzerResult,
    which,
)
from code_architect_optimizer.domain.models import ScanContext

WINDOW_DAYS = 90


class GitHistoryAnalyzer:
    name = "git-history"

    def is_available(self) -> bool:
        if which("git") is None:
            return False
        try:
            p = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True, timeout=30)
            return p.returncode == 0 and p.stdout.strip() == "true"
        except Exception:  # noqa: BLE001
            return False

    def tool_version(self) -> str:
        try:
            p = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=30)
            return (p.stdout or "").strip()[:80]
        except Exception:  # noqa: BLE001
            return "unknown"

    def build_command(self, context: ScanContext) -> list[str]:
        since = (_dt.date.today() - _dt.timedelta(days=WINDOW_DAYS)).isoformat()
        return ["git", "log", f"--since={since}", "--name-only", "--format=COMMIT:%H %an"]

    def parse(self, result: RawAnalyzerResult, context: ScanContext) -> list[MetricObservation]:
        churn: dict[str, int] = {}
        authors: dict[str, set[str]] = {}
        author = ""
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("COMMIT:"):
                author = line[len("COMMIT:"):].strip().split(" ", 1)[-1]
                continue
            if not line or author is None or line.endswith(".pyc") or "__pycache__/" in line:
                continue
            churn[line] = churn.get(line, 0) + 1
            authors.setdefault(line, set()).add(author)
        return [MetricObservation(kind="churn", path=path, data={
            "churn_90d": count,
            "contributors_90d": len(authors.get(path, set())),
        }) for path, count in churn.items()]
