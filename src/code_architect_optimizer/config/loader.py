"""Config loading (Phase 0). TOML config + defaults + sha256 hash."""

from __future__ import annotations

import hashlib
import os
import tomllib
from typing import Any

DEFAULTS: dict[str, Any] = {
    "project": {"name": "unknown", "default_language": "python"},
    "scan": {
        "exclude": [".git/**", ".venv/**", "node_modules/**", "dist/**", "build/**", "generated/**"]
    },
    "thresholds": {
        "file_nloc_review": 300,
        "file_nloc_high": 500,
        "function_nloc_review": 50,
        "cyclomatic_complexity_review": 10,
        "duplication_ratio_review": 0.10,
    },
    "architecture": {"enabled": False},
    "ci": {"mode": "report", "fail_on": ["critical", "high"]},
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_config(repo_root: str, config_name: str = "code-health.toml") -> tuple[dict[str, Any], str]:
    """Return (merged_config, sha256_of_raw_file_or_empty)."""
    path = os.path.join(repo_root, config_name)
    raw = b""
    user: dict[str, Any] = {}
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            raw = fh.read()
        user = tomllib.loads(raw.decode("utf-8"))
    merged = _deep_merge(DEFAULTS, user)
    digest = hashlib.sha256(raw).hexdigest() if raw else "no-config-file"
    return merged, digest
