# CAO public boundary and dependency provenance

This document records the public ownership boundary for Code Architect Optimizer
(CAO). CAO is a hybrid glue layer: it owns the orchestration and report-facing
contracts around independently maintained analyzers, plus its native Git and
standard-library AST analysis. It does not own or redistribute analyzer source.

## Ownership matrix

| Capability | CAO owns | External prerequisite | Public evidence |
| --- | --- | --- | --- |
| Orchestration and analyzer registry | Process invocation, adapter protocol, timeouts, error isolation, normalization, and selection | None beyond the Python package runtime | Bounded metrics, findings, and analyzer-status evidence |
| `scc` integration | Command construction, version capture, JSON parsing, path normalization, and degraded behavior | `scc` executable on `PATH` | File metrics with `source_tool = scc` and captured version |
| Lizard integration | Python API/CSV compatibility, version capture, function normalization, and degraded behavior | `lizard` Python package | Function metrics with `source_tool = lizard` and captured version |
| `jscpd` integration | Command construction, Windows command shim, report parsing, and degraded behavior | `jscpd` executable on `PATH` | Duplication evidence with `source_tool = jscpd` and captured version |
| Git history analysis | Native Git invocation, bounded parsing, and churn/contributor normalization | Git executable and usable repository history | Git-derived provenance and risk inputs |
| Python architecture analysis | Standard-library AST import resolution, dependency boundaries, and cycle evidence | Python 3.12+ | `code-health-architecture` evidence and existing schema-v1 findings |
| Reports and CI delivery | Pydantic contract, redaction, deterministic JSON/Markdown/SARIF rendering, and workflow artifact delivery | None beyond configured CI capabilities | Schema-versioned public reports and bounded evidence |

CAO-native Git and AST analysis must be described as first-party capabilities,
not as wrappers around external architecture tools. The current public repository
is the canonical home; no second repository is required for the glue layer.

## Supported inputs and updates

The package declares Python `>=3.12`. Optional analyzer capabilities remain
independently updateable:

- Install `scc` as an external executable and keep its release/version under
  the repository or deployment's tool-management policy.
- Install Lizard in the Python environment used by `code-health`; the adapter
  records the installed distribution version.
- Install `jscpd` through the supported Node package workflow; on Windows the
  adapter invokes `.cmd`/`.bat` shims through `cmd /c` without shell interpolation.
- Keep Git available for native history evidence.

The CI compatibility baseline currently exercises Python 3.12, Node 22,
Lizard 1.24.1, jscpd 5.4.1, and scc 3.7.0. These are test/deployment inputs,
not vendored package contents or a promise that every future version has
identical output. Dependency updates must rerun adapter contract tests and the
real scan seam, then record changed behavior and compatibility limits.

Missing tools, non-zero exits, timeouts, malformed output, and parser limitations
degrade one analyzer without stopping the scan. The report records unavailable
tools or `parse_complete: false` status evidence. A successful report-mode exit
therefore does not claim complete analyzer coverage.

## Workarounds and upstream issues

The adapters use bounded compatibility workarounds only at their observable
seams. For example, the `jscpd` Windows shim is invoked explicitly, and its two
known report filenames are accepted. The scc adapter accepts both nested
per-file output and direct file entries; it does not invent file metrics when
only an aggregate language summary is returned.

The acceptance record has observed scc 3.7.0 output containing language
summaries without per-file entries in one real checkout. A safe reproduction is:

```text
scc --by-file --format json .
```

Expected behavior is a JSON file-entry list; the observed behavior was an
aggregate language entry without usable `Files` entries. CAO's bounded
workaround is to preserve the aggregate limitation as incomplete analyzer
status rather than infer paths or values. No upstream issue URL is recorded:
the current evidence is a compatibility record, not a complete upstream issue
report meeting the project's reproduction and issue-filing bar. Re-evaluate the
issue-filing decision when the behavior is reproduced with a minimal fixture and
an upstream version response can be attached.

No upstream source, generated copy, binary, cache, or test tree is committed or
modified by CAO. No upstream response is a prerequisite for a bounded CAO
workaround.

## Evidence and raw output

`Provenance` records source tool, tool version, scan time, commit, configuration
hash, estimated-value state, and parse completeness. Public `Evidence` is
bounded and excludes stdout, stderr, and environment fields. Raw analyzer
stdout is retained only under local `.code-health/raw/` for diagnosis; it is not
part of public reports, artifacts, or issue evidence.

The public report remains JSON `schema_version = 1`. This boundary document does
not introduce a parallel glue-layer schema, change risk formulas, alter CI modes,
or change production governance.
