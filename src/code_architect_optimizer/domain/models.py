"""Unified domain data models (Phase 0).

Every metric records its provenance: source tool, tool version, scan time,
git commit, config hash, raw value, estimation flag, parse completeness.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

FileCategory = Literal["production", "test", "generated", "vendor", "config", "unknown"]

REPORT_SCHEMA_VERSION = 1


class Provenance(BaseModel):
    source_tool: str = "unknown"
    tool_version: str = "unknown"
    scanned_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    commit: str = "unknown"
    config_hash: str = "unknown"
    is_estimated: bool = False
    parse_complete: bool = True


class Evidence(BaseModel):
    """Bounded, report-safe evidence for a normalized observation.

    Analyzer stdout/stderr and environment data deliberately have no fields in
    this model.  Renderers can therefore preserve the value needed to explain
    a finding without making raw process output part of the public schema.
    """

    kind: str = "metric"
    source_tool: str = "unknown"
    tool_version: str = "unknown"
    path: str = ""
    metric: str = ""
    raw_value: str | int | float | bool | None = None
    excerpt: str = ""
    provenance: Provenance | None = None


class FileMetric(BaseModel):
    path: str
    language: str = "unknown"
    category: FileCategory = "unknown"
    loc: int = 0
    nloc: int = 0
    complexity: int = 0
    cognitive_complexity: int | None = None
    duplication_ratio: float = 0.0
    fan_in: int = 0
    fan_out: int = 0
    churn_90d: int = 0
    contributors_90d: int = 0
    provenance: Provenance = Field(default_factory=Provenance)


class FunctionMetric(BaseModel):
    file_path: str
    qualified_name: str
    start_line: int = 0
    end_line: int = 0
    nloc: int = 0
    cyclomatic_complexity: int = 0
    parameter_count: int = 0
    nesting_depth: int = 0
    provenance: Provenance = Field(default_factory=Provenance)


class Finding(BaseModel):
    rule_id: str
    severity: Literal["critical", "high", "medium", "low", "info"] = "info"
    path: str
    line: int = 0
    metric: str = ""
    actual: float = 0.0
    threshold: float = 0.0
    evidence_source: str = "unknown"
    message: str = ""


class RiskScore(BaseModel):
    path: str
    risk_score: float = 0.0
    change_pressure: float = 0.0
    refactor_priority: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class ScanContext(BaseModel):
    repo_root: str
    config_path: str = "code-health.toml"
    config_hash: str = "unknown"
    commit: str = "unknown"
    work_dir: str = ".code-health"
    changed_only: bool = False
