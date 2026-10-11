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
