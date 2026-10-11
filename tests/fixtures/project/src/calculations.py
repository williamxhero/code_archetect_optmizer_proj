"""Production calculations used by analyzer fixture tests."""


def complex_decision(value: int, enabled: bool, mode: str) -> str:
    if value < 0:
        return "negative"
    if not enabled:
        return "disabled"
    if mode == "fast":
        if value > 100:
            return "fast-large"
        return "fast-small"
    if mode == "safe":
        if value == 0:
            return "safe-empty"
        if value % 2 == 0:
            return "safe-even"
        return "safe-odd"
    if value > 100 and mode == "batch":
        return "batch-large"
    return "default"


def normalize_values(values: list[int]) -> list[int]:
    result = []
    for value in values:
        if value < 0:
            result.append(0)
        else:
            result.append(value)
    return result


def normalize_values_copy(values: list[int]) -> list[int]:
    result = []
    for value in values:
        if value < 0:
            result.append(0)
        else:
            result.append(value)
    return result
