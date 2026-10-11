from __future__ import annotations

import pytest

from code_architect_optimizer.classification.file_classifier import classify, detect_language


@pytest.mark.parametrize(
    ("path", "category"),
    [
        ("src/service.py", "production"),
        ("tests/test_service.py", "test"),
        ("generated/client.py", "generated"),
        ("vendor/dependency.py", "vendor"),
    ],
)
def test_classify_public_path_categories(path: str, category: str) -> None:
    assert classify(path) == category


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("src/service.py", "python"),
        ("src/component.TSX", "typescript"),
        ("src/worker.go", "go"),
        ("docs/README", "unknown"),
    ],
)
def test_detect_language_uses_extension_mapping(path: str, language: str) -> None:
    assert detect_language(path) == language
