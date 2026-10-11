from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import code_architect_optimizer.cli as cli
from code_architect_optimizer.domain.models import FileMetric, Finding
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.reports import write_report_artifacts


runner = CliRunner()


def test_help_lists_phase_commands_and_deferred_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "init" in result.output
    assert "scan" in result.output
    assert "ai-review" in result.output
    assert "history" in result.output
    assert "not implemented" in result.output.lower()

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
