# Glossary

These definitions are the vocabulary used by the Phase 0+1 MVP. They describe
report fields and CLI behavior rather than implementation details.

- **Baseline** — A schema-versioned snapshot of known findings, including the
  repository, commit, rules, and finding values used by `compare` and CI gates.
- **Change pressure** — The maintenance-pressure component of a risk result,
  derived from Git churn and contributor evidence. It is reported separately
  from structural risk.
- **Evidence** — A bounded, report-safe observation that retains the source tool,
  raw metric value, and provenance needed to explain a finding. Raw analyzer
  stdout/stderr is not evidence in the public report.
- **Finding** — A threshold violation identified by a deterministic rule. It has
  a rule ID, severity, path, metric, actual value, threshold, and evidence source.
- **NCLOC/NLOC** — Non-empty, non-comment physical lines of code as measured by
  an analyzer. The exact counting semantics remain tool- and language-specific;
  NLOC is not a universal cross-tool unit.
- **Provenance** — The source tool and version, scan time, Git commit,
  configuration hash, estimated-value flag, and parse-completeness flag attached
  to a metric or evidence item.
- **Refactor priority** — The ordered investment signal computed from structural
  risk, change pressure, and business-impact weighting. It is not a correctness
  score or a mandatory refactoring instruction.
- **ReportDocument** — The validated in-memory representation of a scan report.
  Its serialized public contract is JSON `schema_version = 1`.
- **Risk score** — The structural-risk component based on size, complexity, and
  duplication signals. It is intentionally separate from change pressure.
- **Unavailable analyzer** — An analyzer that cannot run, times out, exits with
  an error, or cannot be parsed. Scanning continues and the report records the
  diagnostic instead of failing the entire scan.
- **Changed-only scan** — `code-health scan --changed`, which uses usable Git
  working-tree changes; when no usable Git base exists it safely falls back to a
  full scan.
- **Report mode** — The default CI mode: produce findings and return success
  after a completed scan.
- **Ratchet mode** — A CI mode that fails only for newly introduced or worsened
  configured-severity findings compared with a baseline.
- **Strict mode** — A CI mode that fails for any current finding at a configured
  severity, regardless of whether it predates the baseline.
