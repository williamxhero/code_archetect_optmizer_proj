"""Prioritization: rank risks by refactor_priority desc (Phase 1)."""

from code_architect_optimizer.domain.models import RiskScore


def prioritize(risks: list[RiskScore], top: int = 0) -> list[RiskScore]:
    ranked = sorted(risks, key=lambda r: (-r.refactor_priority, -r.risk_score, r.path))
    return ranked[:top] if top > 0 else ranked
