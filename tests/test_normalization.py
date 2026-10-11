from __future__ import annotations

import os

from code_architect_optimizer.analyzers.base import MetricObservation
from code_architect_optimizer.domain.models import FileMetric
from code_architect_optimizer.normalization.metrics import normalize_metrics
from code_architect_optimizer.normalization.paths import normalize_path


def test_normalize_path_removes_relative_prefix_and_repository_root(tmp_path) -> None:
    repository_root = str(tmp_path)
    absolute_path = os.path.join(repository_root, "src", "service.py")

    assert normalize_path("./src/service.py") == "src/service.py"
    assert normalize_path(absolute_path, repository_root) == "src/service.py"


def test_analyzer_observation_becomes_a_classified_metric() -> None:
    observation = MetricObservation(
        kind="file",
        path="tests/test_service.py",
        data={"language": "unknown", "loc": 12, "nloc": 8},
    )
    metric = FileMetric(path=normalize_path(observation.path), **observation.data)

    normalized = normalize_metrics([metric])

    assert normalized[0] is metric
    assert metric.path == "tests/test_service.py"
    assert metric.language == "python"
    assert metric.category == "test"
    assert metric.loc == 12
    assert metric.nloc == 8


def test_normalize_metrics_preserves_explicit_analyzer_values() -> None:
    metric = FileMetric(
        path="vendor/client.js",
        language="javascript",
        category="vendor",
        loc=20,
        nloc=15,
    )

    normalize_metrics([metric])

    assert metric.language == "javascript"
    assert metric.category == "vendor"
    assert metric.loc == 20
    assert metric.nloc == 15
