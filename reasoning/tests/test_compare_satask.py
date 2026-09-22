from __future__ import annotations

from typing import Any

from benchmarks.compare_satask import classify, compare_with_oracle


def test_classify_agreement() -> None:
    assert classify(("value", True), ("value", True)) == "agree"
    assert classify(("value", False), ("value", False)) == "agree"
    assert classify(("value", None), ("value", None)) == "agree"


def test_classify_definite_disagreement_fails() -> None:
    assert classify(("value", True), ("value", False)) == "mismatch"
    assert classify(("value", False), ("value", True)) == "mismatch"


def test_classify_stronger_than_oracle_is_allowed() -> None:
    assert classify(("value", True), ("value", None)) == "stronger"
    assert classify(("value", False), ("value", None)) == "stronger"


def test_classify_weaker_than_oracle_is_reported() -> None:
    assert classify(("value", None), ("value", True)) == "weaker"
    assert classify(("value", None), ("value", False)) == "weaker"


def test_classify_inconsistent_assumptions_are_allowed() -> None:
    assert classify(("error", "ValueError"), ("value", None)) == "inconsistent"
    assert classify(("error", "ValueError"), ("value", False)) == "inconsistent"


def test_classify_unexpected_exception_fails() -> None:
    assert classify(("error", "TypeError"), ("value", True)) == "current-error"
    assert classify(("error", "TypeError"), ("value", None)) == "current-error"


def test_classify_oracle_error_is_unjudged() -> None:
    assert classify(("value", True), ("error", "TypeError")) == "oracle-error"
    assert classify(("error", "ValueError"), ("error", "ValueError")) == "agree"


def test_compare_with_oracle_counts_verdicts() -> None:
    def current(proposition: Any, assumptions: Any,
                early_return: bool = False) -> bool:
        return True

    def oracle(proposition: Any, assumptions: Any) -> None:
        return None

    count, verdicts, failures = compare_with_oracle(
        0, 2, current=current, oracle=oracle)
    assert failures == []
    assert verdicts["stronger"] == count
