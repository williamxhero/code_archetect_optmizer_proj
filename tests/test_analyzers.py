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


def test_jscpd_tool_version_falls_back_to_cmd_for_windows_shim(monkeypatch) -> None:
    shim = r"C:\\tools\\jscpd.cmd"
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args == ["jscpd", "--version"]:
            raise FileNotFoundError
        return SimpleNamespace(stdout="5.4.1\n", stderr="")

    monkeypatch.setattr("code_architect_optimizer.analyzers.jscpd.which", lambda name: shim)
    monkeypatch.setattr("code_architect_optimizer.analyzers.jscpd.os.name", "nt")
    monkeypatch.setattr("code_architect_optimizer.analyzers.jscpd.subprocess.run", fake_run)

    assert JscpdAnalyzer().tool_version() == "5.4.1"
    assert calls[-1][0] == ["cmd", "/c", shim, "--version"]
    assert calls[-1][1].get("shell", False) is False
