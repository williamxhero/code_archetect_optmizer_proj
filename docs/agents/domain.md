# Domain Docs

This repository uses a single-context domain documentation layout.

## Before exploring

- Read `GLOSSARY.md` at the repository root when it exists.
- Read ADRs under `docs/adr/` that touch the area being explored.
- If either file or directory does not exist yet, proceed without treating its absence as a problem. Create them lazily when terminology or architectural decisions are resolved.

## File structure

```text
/
├── GLOSSARY.md
├── docs/adr/
└── src/
```

## Vocabulary rule

Use terms as defined in `GLOSSARY.md` when naming domain concepts in issues, plans, tests, and implementation. If a needed concept is missing, record it for domain modeling rather than silently introducing competing synonyms.

## ADR conflicts

If a proposal contradicts an existing ADR, call out the conflict explicitly and explain whether the ADR should be revisited.
