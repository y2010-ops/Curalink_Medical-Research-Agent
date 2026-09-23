"""Check that model output is normalized to the ASCII the frontend renders."""
from pipeline import normalize_output


def test_normalize():
    raw = "Adding an ICI improves survival【4】 for non‑small‑cell disease."
    assert normalize_output(raw) == "Adding an ICI improves survival[4] for non-small-cell disease."
    assert normalize_output("already [1] clean") == "already [1] clean"
    assert normalize_output("") == ""


if __name__ == "__main__":
    test_normalize()
    print("normalize_output: OK")
