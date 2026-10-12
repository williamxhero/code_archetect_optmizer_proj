from __future__ import annotations

from types import SimpleNamespace

from code_architect_optimizer.analyzers.base import RawAnalyzerResult
from code_architect_optimizer.analyzers.jscpd import JscpdAnalyzer
from code_architect_optimizer.analyzers.lizard import LizardAnalyzer
from code_architect_optimizer.analyzers.scc import SccAnalyzer
from code_architect_optimizer.domain.models import ScanContext


def test_scc_requests_file_level_json_output(tmp_path) -> None:
    command = SccAnalyzer().build_command(ScanContext(repo_root=str(tmp_path)))

    assert command == ["scc", "--by-file", "--format", "json", "."]


def test_scc_parses_file_level_metrics() -> None:
    result = RawAnalyzerResult(
        name="scc",
        available=True,
        stdout='[{"Location":"src/app.py","Language":"Python","Lines":42,"Code":31}]',
    )

    observations = SccAnalyzer().parse(result, ScanContext(repo_root="."))

    assert len(observations) == 1
    assert observations[0].kind == "file"
    assert observations[0].path == "src/app.py"
    assert observations[0].data == {"language": "Python", "loc": 42, "nloc": 31}


def test_lizard_reports_distribution_version(monkeypatch) -> None:
    monkeypatch.setattr(
        "code_architect_optimizer.analyzers.lizard.metadata.version",
        lambda package: "1.17.10",
    )

    assert LizardAnalyzer().tool_version() == "1.17.10"


def test_jscpd_reports_version_from_nonempty_command_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "code_architect_optimizer.analyzers.jscpd.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="\n", stderr="5.4.1\n"),
    )

    assert JscpdAnalyzer().tool_version() == "5.4.1"
