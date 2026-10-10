"""Analyzer adapter protocol + shared runner (Phase 1).

Rules: argv lists only (never shell=True), timeouts, capture stdout/stderr,
record exit codes, missing tools degrade to "unavailable", raw output saved
under .code-health/raw/, secrets never written to reports.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

from code_architect_optimizer.domain.models import ScanContext


@dataclass
class RawAnalyzerResult:
    name: str
    available: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    version: str = "unknown"
    raw_path: str = ""
    error: str = ""


@dataclass
class MetricObservation:
    kind: str  # "file" | "function" | "duplication" | "churn"
    path: str = ""
    data: dict = field(default_factory=dict)


class Analyzer(Protocol):
    name: str

    def is_available(self) -> bool: ...
    def tool_version(self) -> str: ...
    def build_command(self, context: ScanContext) -> list[str]: ...
    def parse(self, result: RawAnalyzerResult, context: ScanContext) -> list[MetricObservation]: ...


SECRET_KEYS = ("token", "password", "secret", "api_key", "apikey", "auth")


def scrub_env(env: dict[str, str]) -> dict[str, str]:
    return {k: ("***" if any(s in k.lower() for s in SECRET_KEYS) else v) for k, v in env.items()}


def run_analyzer(analyzer: Analyzer, context: ScanContext, timeout: int = 300) -> RawAnalyzerResult:
    raw_dir = os.path.join(context.repo_root, context.work_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    if not analyzer.is_available():
        return RawAnalyzerResult(name=analyzer.name, available=False, error="tool not found on PATH")
    cmd = analyzer.build_command(context)
    version = analyzer.tool_version()
    try:
        proc = subprocess.run(
            cmd, cwd=context.repo_root, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        raw_path = os.path.join(raw_dir, f"{analyzer.name}.out")
        with open(raw_path, "w", encoding="utf-8") as fh:
            fh.write(proc.stdout or "")
        return RawAnalyzerResult(
            name=analyzer.name, available=True, exit_code=proc.returncode,
            stdout=proc.stdout or "", stderr=proc.stderr or "",
            version=version, raw_path=raw_path,
        )
    except subprocess.TimeoutExpired:
        return RawAnalyzerResult(name=analyzer.name, available=True, error=f"timeout after {timeout}s")
    except Exception as exc:  # noqa: BLE001 - degraded, never fatal
        return RawAnalyzerResult(name=analyzer.name, available=True, error=str(exc)[:300])


def config_digest_for(context: ScanContext) -> str:
    return context.config_hash or "unknown"


def write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def sha_short(text: str, n: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def which(name: str) -> str | None:
    return shutil.which(name)
