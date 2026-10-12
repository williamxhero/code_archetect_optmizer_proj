"""End-to-end Phase 0+1 scan orchestration."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_architect_optimizer.analyzers import PHASE1_ANALYZERS
from code_architect_optimizer.analyzers.base import (
    Analyzer,
    MetricObservation,
    RawAnalyzerResult,
    run_analyzer,
)
from code_architect_optimizer.classification.file_classifier import detect_language
from code_architect_optimizer.config.loader import load_config
from code_architect_optimizer.domain.models import Evidence, FileMetric, Finding, FunctionMetric, Provenance
from code_architect_optimizer.domain.models import RiskScore, ScanContext
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.normalization.metrics import normalize_metrics
from code_architect_optimizer.normalization.paths import normalize_path
from code_architect_optimizer.reports import write_report_artifacts
from code_architect_optimizer.risk.prioritization import prioritize
from code_architect_optimizer.risk.scoring import score_file
from code_architect_optimizer.selection import select_changed

Runner = Callable[[Analyzer, ScanContext, int], RawAnalyzerResult]


def production_findings(report: ReportDocument) -> list[Finding]:
    """Return findings eligible for default production governance decisions."""
    categories = {metric.path: metric.category for metric in report.files}
    return [
        finding for finding in report.findings
        if categories.get(finding.path, "production") == "production"
    ]


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class ScanService:
    """Run registered analyzers and assemble one validated report document."""

    def __init__(
        self,
        analyzers: Sequence[Analyzer | type[Analyzer]] | None = None,
        *,
        runner: Runner = run_analyzer,
        timeout: int = 300,
    ) -> None:
        self.analyzers = tuple(analyzers or PHASE1_ANALYZERS)
        self.runner = runner
        self.timeout = timeout

    def scan(
        self,
        repo_root: str | os.PathLike[str] = ".",
        *,
        config: Mapping[str, Any] | None = None,
        config_hash: str | None = None,
        config_path: str = "code-health.toml",
        changed_only: bool = False,
        write_reports: bool = True,
        output_dir: str | os.PathLike[str] | None = None,
    ) -> ReportDocument:
        root = str(Path(repo_root).resolve())
        loaded_config, loaded_hash = load_config(root, config_path)
        scan_config = dict(config) if config is not None else loaded_config
        digest = config_hash or (loaded_hash if config is None else _config_digest(scan_config))
        context = ScanContext(
            repo_root=root,
            config_path=config_path,
            config_hash=digest,
            commit=_current_commit(root),
            changed_only=changed_only,
        )
        selection = select_changed(root) if changed_only else None
        changed_paths = selection.paths if selection else None
        scanned_at = datetime.now(timezone.utc).isoformat()
        files: dict[str, FileMetric] = {}
        functions: list[FunctionMetric] = []
        evidence: list[Evidence] = []
        if selection is not None:
            selection_provenance = Provenance(
                source_tool="code-health", scanned_at=scanned_at,
                commit=context.commit, config_hash=context.config_hash,
            )
            if selection.paths is None:
                evidence.append(Evidence(
                    kind="scan-selection", source_tool="code-health", metric="mode",
                    raw_value="full-scan-fallback",
                    excerpt="Changed-only full-scan fallback: no usable default-branch merge base or Git selection failed.",
                    provenance=selection_provenance,
                ))
            else:
                evidence.append(Evidence(
                    kind="scan-selection", source_tool="code-health", metric="merge-base",
                    raw_value=selection.base, provenance=selection_provenance,
                ))
                for path in sorted(selection.paths):
                    if not _excluded(path, scan_config):
                        evidence.append(Evidence(
                            kind="scan-selection", source_tool="code-health", path=path,
                            metric="reason", raw_value="changed" if path in selection.changed else "dependency",
                            excerpt="Static Python imports only; analyzers still run repository-wide.",
                            provenance=selection_provenance,
                        ))
        unavailable_tools: set[str] = set()
        tool_versions: dict[str, str] = {}
        duplicate_lines: dict[str, int] = {}

        for analyzer_entry in self.analyzers:
            analyzer = analyzer_entry() if isinstance(analyzer_entry, type) else analyzer_entry
            try:
                result = self.runner(analyzer, context, self.timeout)
            except Exception as exc:  # noqa: BLE001 - one analyzer never stops a scan
                result = RawAnalyzerResult(
                    name=analyzer.name,
                    available=True,
                    error=str(exc)[:300],
                )
            _ensure_raw_artifact(result, context, analyzer.name)
            if result.available and result.version:
                tool_versions[analyzer.name] = result.version
            if not result.available:
                unavailable_tools.add(analyzer.name)

            observations: list[MetricObservation] = []
            parse_error = False
            if result.available:
                try:
                    parsed = analyzer.parse(result, context)
                    observations = list(parsed or [])
                except Exception:  # noqa: BLE001 - one analyzer never stops a scan
                    parse_error = True

            parse_complete = not parse_error and not result.error and result.exit_code == 0
            if result.available and result.stdout.strip() and not observations:
                parse_complete = False
            if not result.available or not parse_complete:
                status = "unavailable" if not result.available else "parse-incomplete"
                detail = _safe_status_detail(result, parse_error)
                evidence.append(_status_evidence(
                    analyzer.name, result.version, context, scanned_at, status, detail,
                ))

            provenance = Provenance(
                source_tool=analyzer.name,
                tool_version=result.version or "unknown",
                scanned_at=scanned_at,
                commit=context.commit,
                config_hash=context.config_hash,
                parse_complete=parse_complete,
            )
            for observation in observations:
                path = normalize_path(observation.path, root)
                if not path or _excluded(path, scan_config) or not _outside_changed_set(path, changed_paths):
                    continue
                _add_observation(
                    observation, path, provenance, files, functions, duplicate_lines, evidence,
                )

        for path, lines in duplicate_lines.items():
            file_metric = files[path]
            if file_metric.nloc:
                file_metric.duplication_ratio = round(min(max(lines / file_metric.nloc, 0.0), 1.0), 6)

        normalize_metrics(list(files.values()))
        for function in functions:
            function.file_path = normalize_path(function.file_path, root)
        functions = [
            function for function in functions
            if function.file_path in files
            and not _excluded(function.file_path, scan_config)
            and _outside_changed_set(function.file_path, changed_paths)
        ]
        functions_by_file: dict[str, list[FunctionMetric]] = {}
        for function in functions:
            functions_by_file.setdefault(function.file_path, []).append(function)
            if function.file_path in files:
                files[function.file_path].complexity = max(
                    files[function.file_path].complexity,
                    function.cyclomatic_complexity,
                )

        thresholds = scan_config.get("thresholds", {})
        risks: list[RiskScore] = []
        findings: list[Finding] = []
        for file_metric in files.values():
            if file_metric.category != "production":
                continue
            risk, file_findings = score_file(
                file_metric,
                functions_by_file.get(file_metric.path, []),
                thresholds,
            )
            risks.append(risk)
            findings.extend(file_findings)

        risks = prioritize(risks)
        findings.sort(key=lambda finding: (
            _SEVERITY_RANK.get(finding.severity, len(_SEVERITY_RANK)),
            finding.path,
            finding.line,
            finding.rule_id,
            finding.metric,
        ))
        functions.sort(key=lambda function: (
            function.file_path, function.start_line, function.qualified_name, function.end_line,
        ))
        evidence.sort(key=lambda item: (
            item.path, item.metric, item.kind, item.source_tool, str(item.raw_value),
        ))
        report = ReportDocument(
            repository=str(scan_config.get("project", {}).get("name") or Path(root).name),
            commit=context.commit,
            scanned_at=scanned_at,
            config_hash=context.config_hash,
            tool_versions=dict(sorted(tool_versions.items())),
            files=sorted(files.values(), key=lambda item: item.path),
            functions=functions,
            findings=findings,
            risks=risks,
            unavailable_tools=sorted(unavailable_tools),
            evidence=evidence,
        )
        if write_reports:
            write_report_artifacts(report, root, output_dir=output_dir)
        return report


def scan_repository(
    repo_root: str | os.PathLike[str] = ".",
    *,
    config: Mapping[str, Any] | None = None,
    config_hash: str | None = None,
    config_path: str = "code-health.toml",
    changed_only: bool = False,
    analyzers: Sequence[Analyzer | type[Analyzer]] | None = None,
    runner: Runner = run_analyzer,
    timeout: int = 300,
    write_reports: bool = True,
    output_dir: str | os.PathLike[str] | None = None,
) -> ReportDocument:
    """Scan a repository; changed-only falls back to a full scan without a usable Git base."""
    return ScanService(analyzers, runner=runner, timeout=timeout).scan(
        repo_root,
        config=config,
        config_hash=config_hash,
        config_path=config_path,
        changed_only=changed_only,
        write_reports=write_reports,
        output_dir=output_dir,
    )


def _config_digest(config: Mapping[str, Any]) -> str:
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ensure_raw_artifact(result: RawAnalyzerResult, context: ScanContext, analyzer_name: str) -> None:
    raw_dir = Path(context.repo_root) / context.work_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if result.raw_path:
        path = Path(result.raw_path)
    else:
        safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in analyzer_name)
        path = raw_dir / f"{safe_name}.out"
        result.raw_path = str(path)
    if not path.exists():
        path.write_text(result.stdout or "", encoding="utf-8")


def _current_commit(repo_root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True,
            text=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _excluded(path: str, config: Mapping[str, Any]) -> bool:
    if path in {".code-health", "code-health"} or path.startswith((
        ".code-health/", "code-health/",
    )):
        return True
    excludes = config.get("scan", {}).get("exclude", [])
    for pattern in excludes:
        normalized = str(pattern).replace(os.sep, "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if fnmatch.fnmatch(path, normalized) or fnmatch.fnmatch(path, normalized.rstrip("/*")):
            return True
    return False


def _outside_changed_set(path: str, changed_paths: set[str] | None) -> bool:
    return changed_paths is None or path in changed_paths


def _provenance_for_observation(provenance: Provenance, data: Mapping[str, Any]) -> Provenance:
    if data.get("parse_complete") is False:
        return provenance.model_copy(update={"parse_complete": False})
    return provenance


def _add_observation(
    observation: MetricObservation,
    path: str,
    provenance: Provenance,
    files: dict[str, FileMetric],
    functions: list[FunctionMetric],
    duplicate_lines: dict[str, int],
    evidence: list[Evidence],
) -> None:
    data = observation.data if isinstance(observation.data, Mapping) else {}
    observation_provenance = _provenance_for_observation(provenance, data)
    for metric, raw_value in sorted(data.items()):
        if isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
            value: str | int | float | bool | None = raw_value
        else:
            value = str(raw_value)
        evidence.append(Evidence(
            kind=observation.kind,
            source_tool=provenance.source_tool,
            tool_version=provenance.tool_version,
            path=path,
            metric=str(metric),
            raw_value=value,
            excerpt=f"{metric}={value}",
            provenance=observation_provenance,
        ))

    if observation.kind == "file":
        is_new = path not in files
        metric = files.setdefault(path, FileMetric(
            path=path,
            provenance=observation_provenance,
        ))
        metric.language = str(data.get("language") or metric.language or detect_language(path))
        metric.loc = _int(data.get("loc"), metric.loc)
        metric.nloc = _int(data.get("nloc"), metric.nloc)
        if is_new:
            metric.provenance = observation_provenance
    elif observation.kind == "function":
        functions.append(FunctionMetric(
            file_path=path,
            qualified_name=str(data.get("qualified_name") or "unknown"),
            start_line=_int(data.get("start_line")),
            end_line=_int(data.get("end_line")),
            nloc=_int(data.get("nloc")),
            cyclomatic_complexity=_int(data.get("cyclomatic_complexity")),
            parameter_count=_int(data.get("parameter_count")),
            nesting_depth=_int(data.get("nesting_depth")),
            provenance=observation_provenance,
        ))
        files.setdefault(path, FileMetric(path=path, provenance=observation_provenance))
    elif observation.kind == "duplication":
        is_new = path not in files
        files.setdefault(path, FileMetric(path=path, provenance=observation_provenance))
        duplicate_lines[path] = duplicate_lines.get(path, 0) + _int(data.get("duplicated_lines"))
        if data.get("duplication_ratio") is not None:
            files[path].duplication_ratio = _float(data.get("duplication_ratio"))
        if is_new:
            files[path].provenance = observation_provenance
    elif observation.kind == "churn":
        is_new = path not in files
        metric = files.setdefault(path, FileMetric(path=path, provenance=observation_provenance))
        metric.churn_90d = _int(data.get("churn_90d"), metric.churn_90d)
        metric.contributors_90d = _int(data.get("contributors_90d"), metric.contributors_90d)
        if is_new:
            metric.provenance = observation_provenance


def _safe_status_detail(result: RawAnalyzerResult, parse_error: bool) -> str:
    if not result.available:
        return "tool not found on PATH"
    if parse_error:
        return "analyzer output could not be parsed"
    if result.error.startswith("timeout after "):
        return result.error
    if result.exit_code:
        return f"analyzer exited with code {result.exit_code}"
    return "analyzer produced no observations"


def _status_evidence(
    source_tool: str,
    version: str,
    context: ScanContext,
    scanned_at: str,
    status: str,
    detail: str,
) -> Evidence:
    provenance = Provenance(
        source_tool=source_tool,
        tool_version=version or "unknown",
        scanned_at=scanned_at,
        commit=context.commit,
        config_hash=context.config_hash,
        parse_complete=False,
    )
    return Evidence(
        kind="analyzer-status",
        source_tool=source_tool,
        tool_version=version or "unknown",
        metric="status",
        raw_value=status,
        excerpt=detail[:500],
        provenance=provenance,
    )


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


__all__ = ["ScanService", "production_findings", "scan_repository"]
