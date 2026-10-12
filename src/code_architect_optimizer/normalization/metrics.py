"""Metric + path normalization (Phase 0/1)."""

from __future__ import annotations

import os


def normalize_path(path: str, repo_root: str = "") -> str:
    p = path.replace("\\", "/").replace(os.sep, "/").lstrip("./")
    if repo_root:
        root = repo_root.replace("\\", "/").replace(os.sep, "/").rstrip("/")
        if p.startswith(root):
            p = p[len(root):].lstrip("/")
    return p


def normalize_metrics(files: list) -> list:
    """Fill language/category defaults on FileMetric objects in place."""
    from code_architect_optimizer.classification.file_classifier import classify, detect_language

    for f in files:
        if not f.language or f.language == "unknown":
            f.language = detect_language(f.path)
        if not f.category or f.category == "unknown":
            f.category = classify(f.path)  # type: ignore[assignment]
    return files
