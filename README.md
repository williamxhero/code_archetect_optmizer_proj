# Code Architecture Optimizer

Deterministic code-health and architecture-analysis pipeline for AI-assisted development.

> Goal: collect unified structural evidence and help teams decide **whether refactoring is worth it now** — not “yet another linter”.

## Phase 0+1 (current SPEC #1): deterministic MVP

Python orchestrator + `scc` / `Lizard` / `jscpd` / native Git history analysis.
Reproducible JSON + Markdown reports, baseline compare (`report` / `ratchet` / `strict`).
No AI, no Web, no CodeCharta (see SPEC #1 Out of Scope).

## Quick start

```bash
pip install -e ".[dev]"
code-health init
code-health scan
code-health report
code-health compare --baseline .code-health/baseline.json
code-health explain src/example.py
```

See `docs/` (planned) and SPEC issue #1 for scope and acceptance criteria.
