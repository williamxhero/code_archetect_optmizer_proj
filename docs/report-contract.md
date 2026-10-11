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

## Compatibility rule

Adding or removing public fields, changing field meaning, or changing ordering
semantics requires a contract-test update and an explicit `schema_version`
increment. Reports with an unsupported version are not valid Phase 0+1 input.
