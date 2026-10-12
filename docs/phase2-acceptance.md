# Phase 2 SARIF delivery (SPEC #28)

Predecessor: [SPEC #1](https://github.com/williamxhero/code_archetect_optmizer_proj/issues/1),
completed at `a3608c4916d65ac9260e6e7d226f43d0b23e0cd2`.
Implementation tickets: [#29](https://github.com/williamxhero/code_archetect_optmizer_proj/issues/29)
and [#30](https://github.com/williamxhero/code_archetect_optmizer_proj/issues/30).

## Public behavior

```bash
code-health scan
code-health report --format sarif > report.sarif
```

The renderer reads the standard saved JSON report, validates schema version 1,
reuses redaction and stable sorting, and emits SARIF 2.1.0. It does not rerun
analyzers. Rule indexes refer to the sorted driver rule list. Repository-relative
paths are URI encoded. File-level line zero maps to line 1, with the original
value preserved in result properties. Invalid absolute/escaping paths fail with
an operational CLI error. Input JSON/Markdown contracts remain unchanged.

## Verification evidence

Local Windows Python 3.13 verification during this implementation:

- SARIF/CLI/report focused suite: 41 passed.
- Focused suite including workflow checks: 42 passed.
- Full pytest suite including workflow checks: 95 passed.
- Real saved 60-finding report and empty report both validated with jsonschema
  4.26.0 against the SchemaStore SARIF 2.1.0 schema, including format checks.
- SARIF repeated rendering and input-order/timestamp invariance passed.
- Secret redaction, all severity mappings, empty results, malformed schema,
  absent input, URI encoding, and non-repository paths are covered by tests.
- actionlint 1.7.12 passed for `.github/workflows/code-health.yml`.
  ShellCheck was unavailable; actionlint was run with `-shellcheck=`.
- Downloaded actionlint ZIP checksum verified:
  `6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9`.
- `git diff --check` passed after restoring changed files to repository LF endings.

The live GitHub-hosted run, final main test duration, final scan identities, and
remote SHA are recorded in the SPEC issue after delivery. Static checks alone do
not prove a successful hosted upload.

## GitHub Actions configuration

The workflow installs Python 3.12, Node 22, Lizard 1.24.1, jscpd 5.4.1, and scc
3.7.0. scc downloads use the release checksum. Actions are pinned to full commit
SHAs. Full Git checkout preserves native Git history evidence. Availability and
parse-incomplete provenance produce visible warnings.

A normal run uploads only `code-health.sarif` as an Actions artifact. Raw analyzer
outputs and local environments are not uploaded. Code-scanning upload is enabled
by the repository Actions variable `CODE_HEALTH_UPLOAD_SARIF=true`. Enable this
after confirming repository code-scanning entitlement; private repositories need
GitHub Code Security. Fork PRs skip that upload. This configuration does not
activate AI review or change report/ratchet/strict governance policy.

## Scope and remaining limitations

- SQLite, AI/Web, visualization, and architecture dependency checks are deferred.
- Historical worktrees kept under `.claude/worktrees/` remain within this
  checkout's default scan scope; configure exclusions when measuring only the
  main delivery tree. This implementation does not change scan scope.
- Existing incomplete analyzer reports remain incomplete when exported; SARIF
  preserves their coverage diagnostics rather than claiming an empty clean scan.
- End-to-end GitHub code-scanning acceptance depends on repository entitlement
  and explicit upload configuration; the artifact export is available without it.
