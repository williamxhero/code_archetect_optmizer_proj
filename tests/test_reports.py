from __future__ import annotations

import json
from pathlib import Path

from code_architect_optimizer.domain.models import Evidence, FileMetric, Finding, FunctionMetric, Provenance, RiskScore
from code_architect_optimizer.domain.schemas import ReportDocument
from code_architect_optimizer.reports import (
    read_json_report,
    render_json,
    render_markdown,
    render_sarif,
    write_report_artifacts,
)

SNAPSHOT = Path(__file__).parent / "snapshots" / "report.json"


def make_report() -> ReportDocument:
    provenance = Provenance(
        source_tool="scc",
        tool_version="3.2.0",
        scanned_at="2026-10-11T12:34:56Z",
        commit="abc123",
        config_hash="cfg456",
    )
    return ReportDocument(
        repository="example-repository",
        commit="abc123",
        config_hash="cfg456",
        tool_versions={"z-tool": "2.0", "scc": "3.2.0"},
        unavailable_tools=["lizard", "jscpd"],
        files=[
            FileMetric(path="z.py", nloc=10, provenance=provenance),
            FileMetric(path="a.py", nloc=600, provenance=provenance),
        ],
        functions=[
            FunctionMetric(file_path="a.py", qualified_name="sample", start_line=12, end_line=20, provenance=provenance)
        ],
        findings=[
            Finding(rule_id="file.nloc.review", severity="medium", path="a.py", actual=600, threshold=300),
            Finding(rule_id="file.nloc.high", severity="high", path="a.py", actual=600, threshold=500),
        ],
        risks=[
            RiskScore(path="z.py", risk_score=1, refactor_priority=1),
            RiskScore(path="a.py", risk_score=3, refactor_priority=6, reasons=["large file"]),
        ],
        evidence=[
            Evidence(
                source_tool="scc",
                tool_version="3.2.0",
                path="a.py",
                metric="nloc",
                raw_value=600,
                excerpt="nloc=600",
                provenance=provenance,
            )
        ],
    )


def test_json_contract_is_valid_and_matches_snapshot() -> None:
    rendered = render_json(make_report())
    parsed = ReportDocument.model_validate_json(rendered)
    assert parsed.schema_version == 1
    assert parsed.repository == "example-repository"
    assert parsed.commit == "abc123"
    assert parsed.config_hash == "cfg456"
    assert parsed.tool_versions == {"scc": "3.2.0", "z-tool": "2.0"}
    assert parsed.unavailable_tools == ["jscpd", "lizard"]
    assert parsed.files[0].path == "a.py"
    assert parsed.risks[0].path == "a.py"
    assert parsed.files[0].provenance.scanned_at == ""
    assert json.loads(rendered) == json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_rendering_is_invariant_to_input_order_and_timestamps() -> None:
    first = make_report()
    second = make_report()
    first.scanned_at = "2026-10-11T00:00:00Z"
    second.scanned_at = "2026-10-12T00:00:00Z"
    second.files.reverse()
    second.functions.reverse()
    second.findings.reverse()
    second.risks.reverse()
    second.evidence.reverse()
    second.files[0].provenance.scanned_at = "later"
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)
    assert render_sarif(first) == render_sarif(second)


def test_markdown_orders_high_priority_items_first() -> None:
    rendered = render_markdown(make_report())
    assert rendered.index("| 6.0 | 3.0 | 0.0 | `a.py`") < rendered.index("| 1.0 | 1.0 | 0.0 | `z.py`")
    assert rendered.index("| high | `a.py`") < rendered.index("| medium | `a.py`")
    assert rendered.index("## Risks") < rendered.index("## Findings")


def test_renderers_redact_secrets_and_raw_analyzer_output(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_TEST_TOKEN", "env-token-value")
    report = make_report()
    report.findings[0].message = "password=hunter2 token=env-token-value"
    report.evidence[0].excerpt = "Authorization: Bearer bearer-value"
    # Unknown fields are intentionally not in the report schema and therefore
    # cannot smuggle raw analyzer output into the rendered artifact.
    report.evidence[0] = Evidence.model_validate(
        {
            **report.evidence[0].model_dump(),
            "stderr": "raw analyzer stderr must not be emitted",
        }
    )

    rendered_json = render_json(report)
    rendered_markdown = render_markdown(report)
    for rendered in (rendered_json, rendered_markdown, render_sarif(report)):
        assert "hunter2" not in rendered
        assert "env-token-value" not in rendered
        assert "bearer-value" not in rendered
        assert "raw analyzer stderr" not in rendered
        assert "[REDACTED]" in rendered


def test_public_artifact_seam_writes_and_reads_standard_paths(tmp_path) -> None:
    paths = write_report_artifacts(make_report(), tmp_path)
    assert paths["json"] == tmp_path / ".code-health" / "reports" / "report.json"
    assert paths["markdown"] == tmp_path / ".code-health" / "reports" / "report.md"
    loaded = read_json_report(paths["json"])
    assert loaded.repository == "example-repository"
