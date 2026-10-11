"""Default config template rendered by `code-health init`."""

DEFAULT_TOML = """\
[project]
name = "{name}"
default_language = "python"

[scan]
exclude = [
  ".git/**",
  ".venv/**",
  "node_modules/**",
  "dist/**",
  "build/**",
  "generated/**",
]

[thresholds]
file_nloc_review = 300
file_nloc_high = 500
function_nloc_review = 50
cyclomatic_complexity_review = 10
duplication_ratio_review = 0.10

[architecture]
enabled = false

[ci]
mode = "report"
fail_on = ["critical", "high"]
"""
