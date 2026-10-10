"""Lizard adapter: function-level complexity + length (CSV output)."""

from __future__ import annotations

import csv
import io
import subprocess

from code_architect_optimizer.analyzers.base import (
    Analyzer,
    MetricObservation,
    RawAnalyzerResult,
    which,
)
from code_architect_optimizer.domain.models import ScanContext

# Lizard CSV columns: NLOC CCN token param length location file function long_name start end
_LIZARD_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".c", ".cpp", ".h", ".cs", ".rb")


class LizardAnalyzer:
    name = "lizard"

    def is_available(self) -> bool:
        try:
            import lizard  # noqa: F401 - accept library install as availability
            return True
        except ImportError:
            return False

    def tool_version(self) -> str:
        try:
            import lizard as _lz
            return str(getattr(_lz, "__version__", "unknown"))
        except Exception:  # noqa: BLE001
            return "unknown"

    def build_command(self, context: ScanContext) -> list[str]:
        # Unused: lizard runs in-process via its Python API; kept for protocol parity.
        return ["lizard", "--csv", "."]

    def _csv_observations(self, text: str) -> list[MetricObservation]:
        obs: list[MetricObservation] = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                loc = (row.get("location") or "").strip()
                if "@" not in loc:
                    continue
                start_s, end_s = loc.split("@", 1)
                start, end = int(start_s), int(end_s)
                obs.append(MetricObservation(kind="function", path=(row.get("file") or "").strip(), data={
                    "qualified_name": (row.get("function") or row.get("long_name") or "unknown").strip(),
                    "start_line": start,
                    "end_line": end,
                    "nloc": int(row.get("NLOC") or 0),
                    "cyclomatic_complexity": int(row.get("CCN") or 0),
                    "parameter_count": int(row.get("param") or 0),
                    "nesting_depth": 0,  # lizard CSV carries no nesting depth
                }))
            except (ValueError, AttributeError):
                continue
        return obs

    def parse(self, result: RawAnalyzerResult, context: ScanContext) -> list[MetricObservation]:
        if result.available and result.stdout:
            csv_obs = self._csv_observations(result.stdout)
            if csv_obs:
                return csv_obs
        return self._api_scan(context)

    def _api_scan(self, context: ScanContext) -> list[MetricObservation]:
        import os

        import lizard as _lz
        obs: list[MetricObservation] = []
        for root, dirs, files in os.walk(context.repo_root):
            dirs[:] = [d for d in dirs if d not in (".git", ".venv", "node_modules", ".code-health", "__pycache__")]
            for fn in files:
                if not fn.endswith(_LIZARD_EXTS):
                    continue
                full = os.path.join(root, fn)
                try:
                    res = _lz.analyze_file(full)  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001 - one bad file never kills the scan
                    continue
                rel = os.path.relpath(full, context.repo_root).replace(os.sep, "/")
                for func in res.function_list:
                    obs.append(MetricObservation(kind="function", path=rel, data={
                        "qualified_name": getattr(func, "long_name", None) or func.name,
                        "start_line": func.start_line,
                        "end_line": func.end_line,
                        "nloc": func.nloc,
                        "cyclomatic_complexity": func.cyclomatic_complexity,
                        "parameter_count": len(getattr(func, "parameters", []) or []),
                        "nesting_depth": 0,
                    }))
        return obs
