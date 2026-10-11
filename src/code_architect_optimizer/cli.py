"""Minimal CLI seam for the Phase 0+1 scan command."""

from __future__ import annotations

from pathlib import Path

import typer

from code_architect_optimizer.scan import scan_repository

app = typer.Typer(help="Deterministic code-health analysis")


@app.command()
def scan(
    changed: bool = typer.Option(False, "--changed", help="Scan changed files only."),
    repo_root: Path = typer.Argument(Path("."), exists=True, file_okay=False, resolve_path=True),
) -> None:
    """Run the analyzer pipeline and write JSON and Markdown reports."""
    report = scan_repository(repo_root, changed_only=changed)
    report_dir = repo_root / ".code-health" / "reports"
    typer.echo(f"Scanned {len(report.files)} file(s); {len(report.findings)} finding(s).")
    typer.echo(f"JSON report: {report_dir / 'report.json'}")
    typer.echo(f"Markdown report: {report_dir / 'report.md'}")
