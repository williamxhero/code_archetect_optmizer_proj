# Code Architecture Optimizer

Deterministic code-health and architecture-analysis pipeline for AI-assisted development.

> Goal: collect unified structural evidence and help teams decide **whether refactoring is worth it now** — not “yet another linter”.

## Phase 0+1 (SPEC #1): deterministic MVP

Python 3.12+ orchestrator + `scc` / `Lizard` / `jscpd` / native Git history analysis.
Schema-versioned JSON and deterministic Markdown reports support baseline comparison
without requiring AI to make a decision. See the [acceptance handoff](docs/acceptance.md)
for verified behavior and remaining real-analyzer limitations; a degraded scan is
not proof that the checkout has no risks.

## Installation and quick start

```bash
python -m pip install -e ".[dev]"
code-health --help
code-health init                         # in the repository to analyze
code-health scan --update-baseline       # report mode; intentionally seed a baseline
code-health report                       # print Markdown
code-health report --format json         # print JSON
code-health compare --baseline .code-health/baseline.json
code-health explain src/example.py       # replace with a path in the report
```

Python 3.12+ is required. For a non-development installation use
`python -m pip install .`. Activate your virtual environment (or add its scripts
folder to `PATH`) so `code-health` resolves to the same Python installation.

Install optional analyzers separately: `scc` on `PATH`,
`python -m pip install lizard` in the orchestrator's Python environment, and
`npm install -g jscpd` with Node.js and its executable on `PATH`. Native Git
history needs Git on `PATH`. These tools are not required Python dependencies;
without them scanning degrades with explicit diagnostics. Pin analyzer versions
when comparing results over time. Current adapter limitations are documented in
the [acceptance handoff](docs/acceptance.md).

`init` creates `code-health.toml` and `.code-health/raw` and
`.code-health/reports`. It refuses to overwrite an existing configuration; use
`--force` only when replacing it intentionally. This checkout already contains
`code-health.toml`, so skip `init` here. All commands accept a repository path as
their last argument when operating outside the current directory.

`scan --config custom.toml --output-dir artifacts` selects configuration/report
paths relative to the repository. Raw output stays under `.code-health/raw`.
`report`, `compare`, and `explain` read the standard `.code-health/reports` path,
not a custom output directory. `explain` displays thresholds from the current
`code-health.toml`; keep it aligned with the scan configuration.

`scan --changed` currently selects staged/unstaged changes relative to `HEAD`
plus untracked, non-ignored files. It is not a merge-base/branch diff and does not
compute a dependency closure or reduce the external analyzers' workload. Without
a usable Git base it falls back to a full scan.

## Reports and the frozen schema

The public JSON contract is `schema_version = 1`. Its top-level fields are
`schema_version`, `repository`, `commit`, `scanned_at`, `config_hash`,
`tool_versions`, `files`, `functions`, `findings`, `risks`, `unavailable_tools`,
and `evidence`. File/function metrics and evidence retain source-tool provenance;
findings identify an `evidence_source`.

Reports are written to `.code-health/reports/report.json` and `report.md`.
Renderers validate the schema, redact credential-shaped values, omit process
stderr/environment fields, and apply stable ordering. Rendered `scanned_at`
fields are blanked; commit and configuration hash remain. The schema is frozen
by [`tests/snapshots/report.json`](tests/snapshots/report.json) and contract tests;
contract changes require an explicit version increment. See the detailed
[report contract](docs/report-contract.md).

### NCLOC caveat

NCLOC means non-empty, non-comment physical code lines. The `nloc` field preserves
the measuring tool's semantics: scc's file-level `Code` count and Lizard's
function-level NLOC are not interchangeable. Values are not universally
comparable across languages, tools, or versions. Missing measurements can leave
zero-valued placeholders; inspect analyzer-status evidence before trusting them.

Default thresholds trigger findings only when a measured value exceeds the
threshold: file review/high NLOC 300/500, function NLOC 50, cyclomatic complexity
10, and duplication ratio 0.10. The 300-line threshold is a review signal, not a
mandatory split point or an industry standard. Classification distinguishes
production, test, generated, vendor, config, and unknown files. Configured
exclusions omit files; classification alone does not currently exempt test or
generated files from scoring.

Risk output separates structural `risk_score`, Git-derived `change_pressure`,
and `refactor_priority`. Priority uses risk × max(change pressure, 0.5) × business
factor (1.0 in the scan service). Current churn counts commits touching a file,
not added/deleted lines, over a trailing 90-day window.

## Baselines and CI modes

First seed a baseline in default `report` mode with `scan --update-baseline`
(or `compare --update-baseline` using the saved report). To opt into gating,
change `[ci]` in `code-health.toml`:

```toml
[ci]
mode = "ratchet"                     # report / ratchet / strict
fail_on = ["critical", "high"]
```

| Mode | `scan` gate behavior |
| --- | --- |
| `report` | Findings do not fail a completed scan. |
| `ratchet` | Fails only for new/worsened findings at `ci.fail_on` severities. |
| `strict` | Fails for any current finding at `ci.fail_on` severities. |

A failed gate returns exit 1 after writing reports. Both gated modes currently
require an existing valid baseline; seed it before enabling gating. Missing,
corrupt, or incompatible baselines return exit 1 rather than silently passing.
`compare` prints a deterministic summary but does **not** apply a CI gate; a
successful comparison returns 0 regardless of findings. CLI usage errors return
2, while operational/configuration errors return 1.

Baselines contain `schema_version`, `repository`, `commit`, `created_at`, `rules`,
and `known_findings`. Matching uses `rule_id::path::line`: an absent key is `new`,
a larger actual value or more severe level is `worsened`, other matched findings
(including improvements) are `unchanged`, and removed keys are `fixed`.
`--baseline` selects an alternative path. Updates intentionally replace that
snapshot; a failing `scan` gate does not update it. Stored repository/rules are
metadata, not enforced compatibility checks, so compare equivalent repositories,
rules, configurations, and analyzer versions.

## Unavailable tools and safe artifacts

Missing capabilities are listed in `unavailable_tools`. Timeout, non-zero exit,
or malformed output instead creates `analyzer-status` evidence marked
`parse-incomplete`, with `parse_complete: false`. The scan continues with the
remaining evidence; report-mode success does not guarantee complete coverage.

Raw stdout is retained in `.code-health/raw` for diagnosis and is not redacted or
size-limited. Do not publish it. Public reports redact credential-shaped strings
and known credential environment values, but redaction is not a complete secret
scanner: inspect artifacts before sharing them. Keep `.code-health/`, caches,
build outputs, and local environment files out of version control. The supplied
`.gitignore` protects this checkout; add equivalent exclusions to repositories
where you run `init` (it does not edit their ignore files).

## Verification and scope

```bash
python -m pytest tests/test_reports.py tests/test_cli.py tests/test_scan.py -q
python -m pytest -q
# Optional build tooling; not a production dependency:
python -m pip install build
python -m build
```

No additional lint/type-check workflow is currently configured. Review artifacts
and package contents before handoff; see [acceptance results](docs/acceptance.md).

The MVP does not implement `ai-review` or `history`; `--help` marks them as deferred.
AI review, Web/UI, CodeCharta/visualization, SARIF/GitHub Actions, SQLite trends,
SonarQube/Code Maat, dependency/cycle/layer checks, and TypeScript architecture
fixtures remain outside [SPEC #1](https://github.com/williamxhero/code_archetect_optmizer_proj/issues/1).
`[architecture]` is declarative only. Coupling, cognitive complexity, nesting, and
cochange analysis are not implemented; reserved/default fields are not measured
proof of their absence. See [GLOSSARY.md](GLOSSARY.md) for project terminology.
