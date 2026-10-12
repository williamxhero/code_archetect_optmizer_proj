# Report contract (`schema_version = 1`)

The JSON artifact at `.code-health/reports/report.json` is the frozen Phase 0+1
public report contract. It is produced by the same validated model used by the
Markdown renderer; consumers should reject an unknown `schema_version` instead
of guessing at fields.

## Top-level object

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer contract version. It is currently `1`. |
| `repository` | Configured repository name. |
| `commit` | Git commit used for the scan, or `unknown` when Git is unavailable. |
| `scanned_at` | Scan timestamp in the model; rendered artifacts blank this volatile field for reproducibility. |
| `config_hash` | SHA-256 of the raw configuration file, or `no-config-file`. |
| `tool_versions` | Map of analyzer name to detected version. |
| `files` | Unified file metrics and their provenance. |
| `functions` | Unified function metrics and their provenance. |
| `findings` | Deterministically ordered threshold findings. |
| `risks` | Deterministically ordered risk, change-pressure, and refactor-priority values. |
| `unavailable_tools` | Analyzer names that were unavailable or could not complete. |
| `evidence` | Bounded analyzer observations and analyzer-status diagnostics. |

## Determinism and safety

The renderer validates every input with the Pydantic report model, sorts maps and
collections, and normalizes all rendered timestamp fields to an empty string.
The same commit, configuration, analyzer versions, and observations therefore
produce byte-stable JSON and Markdown apart from intentionally retained raw
artifacts under `.code-health/raw/`.

Credential-shaped values are redacted. Fields that could carry raw process output
(`stderr`, `stdout`, and equivalent names) are dropped from public artifacts, and
evidence excerpts are bounded. Raw analyzer stdout is retained only in the local
`.code-health/raw/` directory for diagnosis; it is ignored by Git and must not be
published as a report.

## Provenance

`files`, `functions`, and metric `evidence` include a `provenance` object with:

- `source_tool` and `tool_version`;
- `scanned_at`, `commit`, and `config_hash`;
- `is_estimated`; and
- `parse_complete`.

An unavailable or malformed analyzer contributes status evidence with
`parse_complete: false`, allowing consumers to distinguish missing evidence from
an observed zero value.

## SARIF export

`code-health report --format sarif` reads the saved schema-version-1 report and
emits SARIF 2.1.0. It does not rerun analyzers or change the input JSON schema.
Rule IDs are sorted, results retain deterministic finding order, and the export
uses the same redaction as JSON/Markdown. Critical/high map to `error`, medium to
`warning`, and low/info to `note`. File-level line zero is displayed at line 1;
`original_line` preserves the input value in result properties. Paths must be
repository-relative and are URI-encoded. Absolute or escaping paths are rejected.
Run properties preserve commit, configuration hash, analyzer versions, unavailable
tools, and whether any provenance is parse-incomplete.

## Architecture evidence

When `[architecture].enabled = true`, the scan adds Python dependency evidence
using the `code-health-architecture` tool provenance. File `fan_in` and `fan_out`
values are populated from uniquely resolved repository-local imports. External,
dynamic, malformed, ambiguous, and above-root relative imports are retained as a
bounded `architecture-status` limitation with `parse_complete: false`; the
resolver does not infer a target from an ambiguous match. Cycle observations are
strongly connected groups with stable sorted membership and `architecture-cycle`
evidence. A cycle finding is emitted only when the group contains a production
file, and architecture findings do not enter the existing risk score.

The default is disabled, so reports produced without the architecture setting keep
zero coupling metrics and the existing Phase 0+1 governance behavior.

## Compatibility rule

Adding or removing public fields, changing field meaning, or changing ordering
semantics requires a contract-test update and an explicit `schema_version`
increment. Reports with an unsupported version are not valid Phase 0+1 input.
