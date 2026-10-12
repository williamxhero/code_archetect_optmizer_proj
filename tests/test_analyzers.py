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


def test_scc_parses_nested_by_file_output_for_god_py() -> None:
    result = RawAnalyzerResult(
        name="scc",
        available=True,
        stdout=(
            '[{"Name":"Python","Bytes":1234,"CodeBytes":0,"Lines":160,"Code":118,'
            '"Comment":12,"Blank":30,"Complexity":8,"Count":1,"WeightedComplexity":0,'
            '"Files":[{"Language":"Python","PossibleLanguages":["Python"],'
            '"Filename":"god.py","Extension":"py","Location":"god.py",'
            '"Symlocation":"","Bytes":1234,"Lines":160,"Code":118,"Comment":12,'
            '"Blank":30,"Complexity":8,"WeightedComplexity":0,"Hash":null,'
            '"Binary":false,"Minified":false,"Generated":false,"EndPoint":0,"Uloc":0}]'
            '}]'
        ),
    )

    observations = SccAnalyzer().parse(result, ScanContext(repo_root="."))

    god = next(observation for observation in observations if observation.path == "god.py")
    assert god.data["nloc"] > 0
    assert god.data == {"language": "Python", "loc": 160, "nloc": 118}


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


def test_jscpd_command_ignores_generated_work_and_common_dependency_directories(tmp_path) -> None:
    command = JscpdAnalyzer().build_command(ScanContext(repo_root=str(tmp_path)))
    scan_command = command[3:] if command[:2] == ["cmd", "/c"] else command[1:]

    assert scan_command[0:4] == [".", "--reporters", "json", "--output"]
    assert command[command.index("--ignore") + 1] == (
        ".code-health/**,.git/**,.venv/**,node_modules/**,dist/**,build/**,generated/**"
    )


def test_jscpd_parses_default_report_filename(tmp_path) -> None:
    report_path = tmp_path / ".code-health" / "raw" / "jscpd-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        '{"duplicates": [{"lines": 4, "firstFile": {"name": "a.py"}, '
        '"secondFile": {"name": "b.py"}}]}',
        encoding="utf-8",
    )

    observations = JscpdAnalyzer().parse(
        RawAnalyzerResult(name="jscpd", available=True),
        ScanContext(repo_root=str(tmp_path)),
    )

    assert {item.path: item.data for item in observations} == {
        "a.py": {"duplicated_lines": 4},
        "b.py": {"duplicated_lines": 4},
    }


def test_jscpd_parses_legacy_report_filename(tmp_path) -> None:
    report_path = tmp_path / ".code-health" / "raw" / "jscpd.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        '{"duplicates": [{"lines": 3, "firstFile": {"name": "old.py"}, '
        '"secondFile": {"name": "copy.py"}}]}',
        encoding="utf-8",
    )

    observations = JscpdAnalyzer().parse(
        RawAnalyzerResult(name="jscpd", available=True),
        ScanContext(repo_root=str(tmp_path)),
    )

    assert {item.path: item.data for item in observations} == {
        "old.py": {"duplicated_lines": 3},
        "copy.py": {"duplicated_lines": 3},
    }
