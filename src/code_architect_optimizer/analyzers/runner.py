"""Analyzer registry (Phase 1 set)."""

from code_architect_optimizer.analyzers.git_history import GitHistoryAnalyzer
from code_architect_optimizer.analyzers.jscpd import JscpdAnalyzer
from code_architect_optimizer.analyzers.lizard import LizardAnalyzer
from code_architect_optimizer.analyzers.scc import SccAnalyzer

PHASE1_ANALYZERS = [SccAnalyzer, LizardAnalyzer, JscpdAnalyzer, GitHistoryAnalyzer]
