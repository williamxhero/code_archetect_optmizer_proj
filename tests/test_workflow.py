from __future__ import annotations

import re
from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "code-health.yml"


def test_code_health_workflow_has_pinned_actions_and_least_privilege() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert "contents: read" in text
    assert "security-events: write" in text
    assert "code-health scan --output-dir .code-health/reports ." in text
    assert "code-health report --format sarif > code-health.sarif" in text
    assert "actions/upload-artifact@" in text
    assert "github/codeql-action/upload-sarif@" in text
    actions = re.findall(r"^\s+uses:\s+([^@]+)@([0-9a-f]{40})\s+#", text, re.MULTILINE)
    assert {name for name, _ in actions} == {
        "actions/checkout",
        "actions/setup-python",
        "actions/setup-node",
        "actions/upload-artifact",
        "github/codeql-action/upload-sarif",
    }
    assert len(actions) == 5
    assert "3d9d65b00ca874c2b29151abe7e1480736f5229edc3ce8e4b2791460cdfabf5a" in text
    assert "Unavailable analyzers" in text
    assert "vars.CODE_HEALTH_UPLOAD_SARIF == 'true'" in text
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text
