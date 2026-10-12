# Deterministic analyzer fixtures

The `project/` tree is a small source project with production, test, generated,
vendor, and configuration paths. `src/calculations.py` contains a branching
function and two intentionally duplicated function bodies. Expected categories
and sample analyzer values live in `expected.json`, not in production modules.

Use `materialize_project_fixture(destination)` to copy the project into a fresh
temporary directory. Use `materialize_git_history_fixture(destination)` to copy
a seed tree and create a new local Git repository with three commits from three
fixed authors. Commit dates are generated as fixed offsets from the materializing
run's current date so the commits remain inside the analyzer's trailing 90-day
window. No `.git` directory is stored in the fixture tree.

The `typescript/` tree is the Phase 3 `small-typescript-project` fixture from
[SPEC #31](https://github.com/williamxhero/code_archetect_optmizer_proj/issues/31).
Use `materialize_typescript_fixture(destination)` to copy it to a fresh directory.
Its production, test, generated, vendor, and JSON configuration paths have
expected categories and languages in `expected.json`. `src/calculations.ts`
contains a function with 12 independent branches and two duplicated bodies;
`src/stable value.ts` exercises paths with spaces through SARIF URI encoding.

Contract tests use controlled observations, which do not prove real analyzer
coverage or universal cross-language NLOC equivalence. For a real-tool smoke,
materialize the fixture outside this checkout, run `code-health scan` against it,
and inspect analyzer-status evidence. Use a configuration that does not exclude
`generated/**` if testing visibility of every category. The fixture has no Git
history unless a temporary Git repository is initialized before scanning. No
Node dependencies or TypeScript build step are needed for static measurement.

This fixture is the acceptance foundation for subsequent Phase 3 work.
Dependency-cruiser, Import Linter, Grimp, layer rules, and cycle analysis require
separate implementation tickets and are not provided by this fixture.
