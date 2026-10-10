"""Finding rules registry (Phase 1). Rule ids emitted by scoring."""

RULES = {
    "file.nloc.review": "文件行数超过模块化审查触发线（默认 300）",
    "file.nloc.high": "文件行数超过高线（默认 500）",
    "file.duplication.high": "重复代码比例超过阈值（默认 10%）",
    "function.complexity.high": "函数圈复杂度超过审查阈值（默认 10）",
    "function.nloc.high": "函数行数超过审查阈值（默认 50）",
}
