from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import code_architect_optimizer.cli as cli
from code_architect_optimizer.domain.models import (
    Evidence,
    FileMetric,
    Finding,
    FunctionMetric,
    RiskScore,
)
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.reports import write_report_artifacts


runner = CliRunner()


def test_help_lists_phase_commands_and_deferred_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "init" in result.output
    assert "scan" in result.output
    assert "report" in result.output
    assert "explain" in result.output
    assert "ai-review" in result.output
    assert "history" in result.output
    assert "not implemented" in result.output.lower()

    report_help = runner.invoke(cli.app, ["report", "--help"])
    assert report_help.exit_code == 0
    assert "--format" in report_help.output
    explain_help = runner.invoke(cli.app, ["explain", "--help"])
    assert explain_help.exit_code == 0
    assert "FILE" in explain_help.output

    scan_help = runner.invoke(cli.app, ["scan", "--help"])
    assert scan_help.exit_code == 0
    assert "--changed" in scan_help.output
    assert "--config" in scan_help.output
    assert "--output-dir" in scan_help.output


def test_init_creates_config_and_workspace_without_overwriting(tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["init", str(tmp_path)])

    assert result.exit_code == 0
    config = tmp_path / "code-health.toml"
    assert config.is_file()
    assert (tmp_path / ".code-health" / "raw").is_dir()
    assert (tmp_path / ".code-health" / "reports").is_dir()
    assert f'name = "{tmp_path.name}"' in config.read_text(encoding="utf-8")

    config.write_text("user configuration\n", encoding="utf-8")
    refused = runner.invoke(cli.app, ["init", str(tmp_path)])
    assert refused.exit_code == 1
    assert "use --force" in refused.output
    assert config.read_text(encoding="utf-8") == "user configuration\n"

    forced = runner.invoke(cli.app, ["init", "--force", str(tmp_path)])
    assert forced.exit_code == 0
    assert "user configuration" not in config.read_text(encoding="utf-8")
    assert "[project]" in config.read_text(encoding="utf-8")


def test_scan_runner_writes_reports_and_keeps_findings_non_fatal(
    tmp_path: Path, monkeypatch
) -> None:
    report = ReportDocument(
        repository="cli-project",
        files=[FileMetric(path="src/example.py")],
        findings=[Finding(rule_id="file.nloc.review", severity="medium", path="src/example.py")],
        unavailable_tools=["scc"],
    )

    def fake_scan(
        repo_root: Path,
        *,
        config_path: str,
        changed_only: bool,
        output_dir: Path | None,
    ) -> ReportDocument:
        assert config_path == "custom.toml"
        assert changed_only is True
        write_report_artifacts(report, repo_root, output_dir=output_dir)
        return report

    monkeypatch.setattr(cli, "scan_repository", fake_scan)
    (tmp_path / "custom.toml").write_text("[project]\nname = 'custom'\n", encoding="utf-8")
    output_dir = tmp_path / "artifacts"
    result = runner.invoke(
        cli.app,
        [
            "scan",
            "--changed",
            "--config",
            "custom.toml",
            "--output-dir",
            str(output_dir),
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "Scanned 1 file(s); 1 finding(s)." in result.output
    assert "Unavailable analyzers: scc" in result.output
    assert (output_dir / "report.json").is_file()
    assert (output_dir / "report.md").is_file()


def test_scan_reports_invalid_configuration_as_cli_error(tmp_path: Path) -> None:
    (tmp_path / "code-health.toml").write_text("invalid = [\n", encoding="utf-8")

    result = runner.invoke(cli.app, ["scan", str(tmp_path)])

    assert result.exit_code == 1
    assert "Error: scan could not complete:" in result.output


def test_report_prints_saved_json_or_markdown_and_rejects_missing_artifacts(tmp_path: Path) -> None:
    report = ReportDocument(repository="cli-project", commit="abc123", files=[FileMetric(path="src/example.py")])
    write_report_artifacts(report, tmp_path)

    markdown = runner.invoke(cli.app, ["report", str(tmp_path)])
    assert markdown.exit_code == 0
    assert "# Code Health Report" in markdown.output

    json_result = runner.invoke(cli.app, ["report", "--format", "json", str(tmp_path)])
    assert json_result.exit_code == 0
    assert '"repository": "cli-project"' in json_result.output

    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    missing = runner.invoke(cli.app, ["report", str(missing_root)])
    assert missing.exit_code == 1
    assert "run 'code-health scan' first" in missing.output


def test_report_rejects_unknown_format_and_corrupt_json(tmp_path: Path) -> None:
    invalid_format = runner.invoke(cli.app, ["report", "--format", "xml", str(tmp_path)])
    assert invalid_format.exit_code == 1
    assert "--format must be 'json' or 'markdown'" in invalid_format.output

    report_dir = tmp_path / ".code-health" / "reports"
    report_dir.mkdir(parents=True)
    (report_dir / "report.json").write_text("not json", encoding="utf-8")
    (report_dir / "report.md").write_text("stale", encoding="utf-8")
    corrupt = runner.invoke(cli.app, ["report", str(tmp_path)])
    assert corrupt.exit_code == 1
    assert "could not read report" in corrupt.output


def test_explain_normalizes_path_and_shows_report_evidence_without_secrets(tmp_path: Path) -> None:
    report = ReportDocument(
        repository="cli-project",
        files=[FileMetric(path="src/example.py", nloc=12, complexity=4)],
        functions=[FunctionMetric(file_path="src/example.py", qualified_name="run", nloc=12)],
        findings=[Finding(rule_id="file.nloc.review", severity="medium", path="src/example.py", actual=12, threshold=10)],
        risks=[RiskScore(path="src/example.py", risk_score=2, change_pressure=3, refactor_priority=6)],
        evidence=[Evidence(path="src/example.py", metric="nloc", raw_value=12, excerpt="token=do-not-print")],
    )
    write_report_artifacts(report, tmp_path)
    (tmp_path / "code-health.toml").write_text(
        "[thresholds]\nfile_nloc_review = 10\n", encoding="utf-8"
    )

    result = runner.invoke(cli.app, ["explain", "./src/../src/example.py", str(tmp_path)])

    assert result.exit_code == 0
    assert "File: src/example.py" in result.output
    assert '"nloc": 12' in result.output
    assert '"refactor_priority": 6.0' in result.output
    assert '"file_nloc_review": 10' in result.output
    assert "[REDACTED]" in result.output
    assert "do-not-print" not in result.output

    unknown = runner.invoke(cli.app, ["explain", "src/missing.py", str(tmp_path)])
    assert unknown.exit_code == 1
    assert "file not found in the latest scan report" in unknown.output
