"""Typer CLI for the deterministic Phase 0+1 MVP."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, NoReturn

import typer

from code_architect_optimizer.baseline.compare import BaselineError, compare as compare_baseline, gate
from code_architect_optimizer.baseline.store import (
    load_baseline_checked,
    save_baseline_file,
)
from code_architect_optimizer.config.defaults import DEFAULT_TOML
from code_architect_optimizer.config.loader import DEFAULTS, load_config
from code_architect_optimizer.reports import read_json_report, render_json, render_markdown
from code_architect_optimizer.scan import scan_repository

app = typer.Typer(
    help=(
        "Deterministic code-health analysis.\n\n"
        "Implemented commands: init, scan, report, compare, explain.\n"
        "Not implemented in this phase: ai-review, history."
    )
)


def _error(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


def _validate_config(config: dict[str, Any]) -> None:
    for section in DEFAULTS:
        if not isinstance(config[section], dict):
            raise ValueError(f"[{section}] must be a TOML table")
    for key in ("name", "default_language"):
        if not isinstance(config["project"][key], str):
            raise ValueError(f"project.{key} must be a string")
    excludes = config["scan"]["exclude"]
    if not isinstance(excludes, list) or any(not isinstance(item, str) for item in excludes):
        raise ValueError("scan.exclude must be an array of strings")
    for key in DEFAULTS["thresholds"]:
        value = config["thresholds"][key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"thresholds.{key} must be a finite nonnegative number")
    mode = config["ci"].get("mode")
    if mode not in {"report", "ratchet", "strict"}:
        raise ValueError("ci.mode must be 'report', 'ratchet', or 'strict'")
    fail_on = config["ci"].get("fail_on")
    if not isinstance(fail_on, list) or any(item not in {"critical", "high", "medium", "low", "info"} for item in fail_on):
        raise ValueError("ci.fail_on must be an array of severities")


def _selected_path(repo_root: Path, selected: Path | None, default: str) -> Path:
    path = selected or Path(default)
    return path if path.is_absolute() else repo_root / path


def _baseline_rules(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("thresholds", {}))


def _display_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)


def _finding_detail(category: str, finding: dict[str, Any]) -> str:
    if category == "fixed":
        key = str(finding.get("key", ""))
        rule_id, path, line = (key.split("::", 2) + ["", "", ""])[:3]
        severity = finding.get("severity", "info")
        return f"FIXED: {severity} {rule_id} {path}:{line} (was {_display_number(finding.get('actual', ''))})"
    severity = finding.get("severity", "info")
    rule_id = finding.get("rule_id", "unknown")
    path = finding.get("path", "")
    line = finding.get("line", 0)
    detail = f"({_display_number(finding.get('actual', ''))} > {_display_number(finding.get('threshold', ''))})"
    return f"{category.upper()}: {severity} {rule_id} {path}:{line} {detail}"


def _print_comparison(comparison: dict[str, Any]) -> None:
    categories = ("new", "worsened", "unchanged", "fixed")
    counts = ", ".join(f"{len(comparison[name])} {name}" for name in categories)
    typer.echo(f"Baseline comparison: {counts}")
    for category in categories:
        for finding in comparison[category]:
            typer.echo(_finding_detail(category, finding))


@app.command("init")
def init(
    repo_root: Path = typer.Argument(Path("."), exists=True, file_okay=False, resolve_path=True),
    overwrite: bool = typer.Option(
        False,
        "--force",
        "--overwrite",
        help="Replace an existing code-health.toml.",
    ),
) -> None:
    """Create the default configuration and code-health workspace."""
    config_path = repo_root / "code-health.toml"
    if config_path.is_symlink():
        _error(f"{config_path} is a symlink; choose a regular configuration file")
    if config_path.exists() and not overwrite:
        _error(f"{config_path} already exists; use --force to replace it")

    try:
        (repo_root / ".code-health" / "raw").mkdir(parents=True, exist_ok=True)
        (repo_root / ".code-health" / "reports").mkdir(parents=True, exist_ok=True)
        name = json.dumps(repo_root.name or repo_root.anchor, ensure_ascii=False)[1:-1]
        with config_path.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as config_file:
            config_file.write(DEFAULT_TOML.format(name=name))
    except OSError as exc:
        _error(f"could not initialize {repo_root}: {exc}")

    typer.echo(f"Initialized code-health in {repo_root}")
    typer.echo(f"Config: {config_path}")


@app.command("scan")
def scan(
    changed: bool = typer.Option(False, "--changed", help="Scan changed files only."),
    config_path: Path | None = typer.Option(
        None,
        "--config",
        "--config-path",
        help="Configuration file relative to the repository (default: code-health.toml or defaults).",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "--output",
        help="Report directory relative to the repository (default: .code-health/reports).",
    ),
    baseline: Path | None = typer.Option(None, "--baseline", help="Baseline file for CI gating."),
    update_baseline: bool = typer.Option(False, "--update-baseline", help="Write the completed scan as the baseline."),
    repo_root: Path = typer.Argument(Path("."), exists=True, file_okay=False, resolve_path=True),
) -> None:
    """Run the analyzer pipeline and write JSON and Markdown reports."""
    selected_config = config_path or Path("code-health.toml")
    if config_path is not None:
        config_file = selected_config if selected_config.is_absolute() else repo_root / selected_config
        if not config_file.is_file():
            _error(f"configuration file does not exist: {config_file}")

    report_dir = (
        output_dir
        if output_dir is None or output_dir.is_absolute()
        else repo_root / output_dir
    )
    try:
        config, _ = load_config(str(repo_root), str(selected_config))
        _validate_config(config)
        report = scan_repository(
            repo_root,
            config_path=str(selected_config),
            changed_only=changed,
            output_dir=report_dir,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary must return an actionable error
        _error(f"scan could not complete: {exc}")

    report_dir = report_dir or repo_root / ".code-health" / "reports"
    typer.echo(f"Scanned {len(report.files)} file(s); {len(report.findings)} finding(s).")
    if report.unavailable_tools:
        typer.echo(
            "Unavailable analyzers: " + ", ".join(report.unavailable_tools),
            err=True,
        )
    typer.echo(f"JSON report: {report_dir / 'report.json'}")
    typer.echo(f"Markdown report: {report_dir / 'report.md'}")

    mode = config["ci"]["mode"]
    fail_on = config["ci"]["fail_on"]
    baseline_file = _selected_path(repo_root, baseline, ".code-health/baseline.json")
    if mode == "report":
        comparison = {"new": [], "worsened": [], "fixed": [], "unchanged": []}
    else:
        try:
            loaded_baseline = load_baseline_checked(str(baseline_file))
        except BaselineError as exc:
            _error(f"could not load baseline at {baseline_file}: {exc}")
        comparison = compare_baseline(report.findings, loaded_baseline)

    passed, reason = gate(mode, comparison, fail_on, report.findings)
    typer.echo(f"CI gate: {reason}")
    if not passed:
        raise typer.Exit(code=1)
    if update_baseline:
        try:
            safe_report = read_json_report(report_dir / "report.json")
            save_baseline_file(
                str(baseline_file), safe_report.repository, safe_report.commit,
                _baseline_rules(config), safe_report.findings,
            )
        except (OSError, ValueError) as exc:
            _error(f"could not write baseline at {baseline_file}: {exc}")
        typer.echo(f"Baseline: {baseline_file}")


@app.command("compare")
def compare(
    baseline: Path = typer.Option(
        Path(".code-health/baseline.json"),
        "--baseline",
        help="Baseline JSON file to compare against.",
    ),
    update_baseline: bool = typer.Option(
        False,
        "--update-baseline",
        help="Write the current report findings as the selected baseline.",
    ),
    repo_root: Path = typer.Argument(Path("."), exists=True, file_okay=False, resolve_path=True),
) -> None:
    """Compare the saved scan report with a known-findings baseline."""
    report_path = repo_root / ".code-health" / "reports" / "report.json"
    if not report_path.is_file():
        _error(f"no scan report found at {report_path}; run 'code-health scan' first")
    baseline_file = _selected_path(repo_root, baseline, ".code-health/baseline.json")
    try:
        report_document = read_json_report(report_path)
    except (OSError, ValueError) as exc:
        _error(f"could not read report at {report_path}: {exc}")

    if baseline_file.is_file():
        try:
            baseline_document = load_baseline_checked(str(baseline_file))
        except BaselineError as exc:
            _error(f"could not load baseline at {baseline_file}: {exc}")
    elif update_baseline:
        baseline_document = None
    else:
        _error(f"could not load baseline at {baseline_file}: baseline does not exist")

    comparison = compare_baseline(report_document.findings, baseline_document)
    _print_comparison(comparison)
    if update_baseline:
        try:
            config, _ = load_config(str(repo_root), "code-health.toml")
            _validate_config(config)
            save_baseline_file(
                str(baseline_file), report_document.repository, report_document.commit,
                _baseline_rules(config), report_document.findings,
            )
        except (OSError, ValueError) as exc:
            _error(f"could not update baseline at {baseline_file}: {exc}")
        typer.echo(f"Baseline: {baseline_file}")


@app.command("report")
def report(
    format: str = typer.Option("markdown", "--format", help="Report format: json or markdown."),
    repo_root: Path = typer.Argument(Path("."), exists=True, file_okay=False, resolve_path=True),
) -> None:
    """Print the saved JSON or Markdown scan report."""
    if format not in {"json", "markdown"}:
        _error("--format must be 'json' or 'markdown'")

    report_dir = repo_root / ".code-health" / "reports"
    artifact = report_dir / ("report.json" if format == "json" else "report.md")
    if not artifact.is_file():
        _error(f"no {format} report found at {artifact}; run 'code-health scan' first")

    try:
        document = read_json_report(report_dir / "report.json")
        output = render_json(document) if format == "json" else render_markdown(document)
    except (OSError, ValueError) as exc:
        _error(f"could not read report at {report_dir}: {exc}")
    typer.echo(output, nl=False)


@app.command("explain")
def explain(
    file: str = typer.Argument(
        ...,
        metavar="FILE",
        help="Repository-relative path of the file to explain.",
    ),
    repo_root: Path = typer.Argument(Path("."), exists=True, file_okay=False, resolve_path=True),
) -> None:
    """Explain a file's metrics, findings, risk, and evidence."""
    report_dir = repo_root / ".code-health" / "reports"
    report_path = report_dir / "report.json"
    if not report_path.is_file():
        _error(f"no scan report found at {report_path}; run 'code-health scan' first")

    try:
        document = read_json_report(report_path)
        config, _ = load_config(str(repo_root), "code-health.toml")
        _validate_config(config)
    except (OSError, ValueError) as exc:
        _error(f"could not read report or configuration: {exc}")

    requested_path = Path(file)
    absolute_path = (
        requested_path.resolve()
        if requested_path.is_absolute()
        else (repo_root / requested_path).resolve()
    )
    try:
        relative_path = absolute_path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        _error("file is outside the repository")

    payload = json.loads(render_json(document))
    metrics = next((item for item in payload["files"] if item["path"] == relative_path), None)
    if metrics is None:
        _error("file not found in the latest scan report")

    findings = [item for item in payload["findings"] if item["path"] == relative_path]
    functions = [item for item in payload["functions"] if item["file_path"] == relative_path]
    risks = [item for item in payload["risks"] if item["path"] == relative_path]
    evidence = [item for item in payload["evidence"] if item["path"] == relative_path]
    typer.echo(f"File: {relative_path}")
    typer.echo("Metrics:")
    typer.echo(json.dumps(metrics, ensure_ascii=False, sort_keys=True, indent=2))
    typer.echo("Thresholds:")
    typer.echo(json.dumps(config["thresholds"], ensure_ascii=False, sort_keys=True, indent=2))
    typer.echo("Findings:")
    typer.echo(json.dumps(findings, ensure_ascii=False, sort_keys=True, indent=2))
    typer.echo("Functions:")
    typer.echo(json.dumps(functions, ensure_ascii=False, sort_keys=True, indent=2))
    typer.echo("Risk:")
    typer.echo(json.dumps(risks, ensure_ascii=False, sort_keys=True, indent=2))
    typer.echo("Evidence:")
    typer.echo(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
