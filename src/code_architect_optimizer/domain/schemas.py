"""Report JSON schema (Phase 0, frozen at schema_version=1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from code_architect_optimizer.domain.models import (
    REPORT_SCHEMA_VERSION,
    Evidence,
    FileMetric,
    Finding,
    FunctionMetric,
    RiskScore,
)


class ReportDocument(BaseModel):
    """Validated input/output document for the deterministic report renderers."""

    schema_version: Literal[REPORT_SCHEMA_VERSION] = REPORT_SCHEMA_VERSION
    repository: str = "unknown"
    commit: str = "unknown"
    scanned_at: str = ""
    config_hash: str = "unknown"
    tool_versions: dict[str, str] = Field(default_factory=dict)
    files: list[FileMetric] = Field(default_factory=list)
    functions: list[FunctionMetric] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    risks: list[RiskScore] = Field(default_factory=list)
    unavailable_tools: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
