"""Validated, deterministic local Python dependency-boundary policies."""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping


class BoundaryPolicyError(ValueError):
    """The configured architecture boundary policy cannot be evaluated."""


@dataclass(frozen=True)
class BoundaryPolicy:
    """A normalized layer-pattern and allowed-direction policy."""

    layers: tuple[tuple[str, tuple[str, ...]], ...]
    allowed: tuple[tuple[str, tuple[str, ...]], ...]
    config_hash: str

    @property
    def layer_map(self) -> dict[str, tuple[str, ...]]:
        return dict(self.layers)

    @property
    def allowed_map(self) -> dict[str, tuple[str, ...]]:
        return dict(self.allowed)

    def matches(self, path: str) -> tuple[str, ...]:
        """Return all matching layers; multiple matches are intentionally ambiguous."""
        normalized = path.replace("\\", "/")
        return tuple(
            name for name, patterns in self.layers
            if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)
        )

    def permits(self, source: str, target: str) -> bool:
        return target in self.allowed_map.get(source, ())


def parse_boundary_policy(architecture: Mapping[str, Any], *, enabled: bool) -> BoundaryPolicy | None:
    """Parse supported policy syntax and reject malformed declarations.

    The canonical TOML shape is either ``architecture.boundaries`` or
    ``architecture.policy`` with ``layers`` and ``allowed`` tables.  Each layer
    value is a list of repository-relative glob patterns; ``allowed`` maps a
    source layer to target layer names.
    """
    raw = architecture.get("boundaries")
    if raw is None:
        raw = architecture.get("policy")
    if raw is None or (isinstance(raw, Mapping) and raw.get("enabled") is False):
        return None
    if not enabled:
        raise BoundaryPolicyError("architecture boundary policy requires architecture.enabled = true")
    if not isinstance(raw, Mapping):
        raise BoundaryPolicyError("[architecture.boundaries] must be a TOML table")

    layers_raw = raw.get("layers", raw.get("groups"))
    allowed_raw = raw.get("allowed", raw.get("allow", {}))
    if layers_raw is None:
        # Permit the concise [architecture.boundaries.layers] table only; an
        # empty table remains a configured policy and is reported as such.
        layers_raw = {}
    if not isinstance(layers_raw, Mapping):
        raise BoundaryPolicyError("architecture boundary layers must be a TOML table")
    if not isinstance(allowed_raw, Mapping):
        raise BoundaryPolicyError("architecture boundary allowed must be a TOML table")

    layer_names: set[str] = set()
    normalized_layers: list[tuple[str, tuple[str, ...]]] = []
    for name, patterns in sorted(layers_raw.items(), key=lambda item: str(item[0])):
        if not isinstance(name, str) or not name or name in layer_names:
            raise BoundaryPolicyError("architecture boundary layer names must be unique non-empty strings")
        layer_names.add(name)
        if not isinstance(patterns, list) or not patterns or any(not isinstance(pattern, str) for pattern in patterns):
            raise BoundaryPolicyError(f"architecture boundary layer {name!r} patterns must be a non-empty string list")
        normalized_patterns: list[str] = []
        for pattern in patterns:
            normalized = pattern.replace("\\", "/")
            if not normalized or normalized.startswith("/") or PurePosixPath(normalized).is_absolute() or ".." in PurePosixPath(normalized).parts:
                raise BoundaryPolicyError(f"architecture boundary pattern {pattern!r} must be repository-relative")
            normalized_patterns.append(normalized)
        normalized_layers.append((name, tuple(sorted(set(normalized_patterns)))))

    normalized_allowed: list[tuple[str, tuple[str, ...]]] = []
    for source, targets in sorted(allowed_raw.items(), key=lambda item: str(item[0])):
        if not isinstance(source, str) or source not in layer_names:
            raise BoundaryPolicyError(f"architecture boundary allowed source {source!r} is not a declared layer")
        if not isinstance(targets, list) or any(not isinstance(target, str) for target in targets):
            raise BoundaryPolicyError(f"architecture boundary allowed targets for {source!r} must be a string list")
        unknown = sorted(set(targets) - layer_names)
        if unknown:
            raise BoundaryPolicyError(f"architecture boundary allowed targets for {source!r} are undeclared: {unknown}")
        normalized_allowed.append((source, tuple(sorted(set(targets)))))

    canonical = {"layers": dict(normalized_layers), "allowed": dict(normalized_allowed)}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return BoundaryPolicy(tuple(normalized_layers), tuple(normalized_allowed), digest)


__all__ = ["BoundaryPolicy", "BoundaryPolicyError", "parse_boundary_policy"]
