from src.calculations import complex_decision


def test_complex_decision() -> None:
    assert complex_decision(1, True, "safe") == "safe-odd"
