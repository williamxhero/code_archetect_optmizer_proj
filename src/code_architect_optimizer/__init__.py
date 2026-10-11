"""Code Architect Optimizer — deterministic code-health pipeline (Phase 0+1 MVP)."""

from code_architect_optimizer.domain.models import (
    FileMetric,
    Finding,
    FunctionMetric,
    ScanContext,
)
from code_architect_optimizer.scan import ScanService, scan_repository

__all__ = [
    "FileMetric",
    "Finding",
    "FunctionMetric",
    "ScanContext",
    "ScanService",
    "scan_repository",
]
__version__ = "0.1.0"
