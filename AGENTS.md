# Agent Instructions

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.

## Third-party dependency policy

- Third-party analyzers and libraries (for example `scc`, Lizard, and `jscpd`)
  are external dependencies, never source copies in this repository.
- Never vendor, mirror, paste, fork, or commit upstream source code, generated
  copies, binaries, caches, or their test trees into this repository.
- The repository may contain only our adapters, glue code, configuration
  contracts, fixtures authored for our tests, provenance handling, and tests
  for observable integration behavior.
- Keep third-party dependencies independently updateable through supported
  package managers or documented external binaries. Pin or record versions
  where reproducibility requires it, without copying the dependency source.
- When an upstream limitation or defect is found, first implement a bounded
  compatibility/workaround in our glue layer, preserve evidence and the
  upstream version, and file an issue in the upstream repository when an
  issue is warranted. Link the upstream issue from our issue/SPEC.
- On every dependency update, run the adapter contract tests and the real
  scan seam; record changed behavior, compatibility limits, and upstream
  issue references. Do not modify upstream code locally.

## Project scope

This repository will develop a deterministic code-health and architecture-analysis pipeline for AI-assisted software development.

The first implementation phase is limited to a reproducible MVP using external analyzers and native Git history analysis. It should produce explainable JSON and Markdown reports, preserve analyzer evidence, and avoid making AI review a required CI decision-maker.
