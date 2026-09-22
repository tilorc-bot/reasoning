"""Tests for the audit helpers in ``tools/check_soundness.py``."""
from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path
from typing import Any

from sympy import I, Q, S, symbols

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_soundness.py"
_spec = importlib.util.spec_from_file_location("check_soundness", _TOOL)
assert _spec is not None and _spec.loader is not None
check_soundness: Any = importlib.util.module_from_spec(_spec)
sys.modules["check_soundness"] = check_soundness
_spec.loader.exec_module(check_soundness)

x, y = symbols("x y")


def _stub(result: Any, error: Exception | None = None) -> Any:
    def satask_fn(proposition: Any, assumptions: Any = True,
                  **kwargs: Any) -> Any:
        if error is not None:
            raise error
        return result
    return satask_fn


def _audit(case: Any, satask_fn: Any, ask_fn: Any = None,
           use_oracle: bool = False, strict: bool = False) -> Any:
    rng = random.Random("audit")
    return check_soundness.audit_case(
        case, (x,), (), rng, satask_fn, ask_fn, use_oracle=use_oracle,
        strict=strict)


def test_ground_truth_evaluates_ground_atoms() -> None:
    formula = Q.positive(x) & ~Q.zero(x)
    assert check_soundness.ground_truth(formula, {x: S(2)}) is True
    assert check_soundness.ground_truth(formula, {x: S.Zero}) is False
    assert check_soundness.ground_truth(Q.prime(x) & ~Q.prime(x), {x: S(2)}) is False
    assert check_soundness.ground_truth(True, {}) is True


def test_ground_truth_returns_none_for_unknown_atoms() -> None:
    assert check_soundness.ground_truth(Q.hermitian(x + y), {x: x, y: y}) is None


def test_find_models_returns_satisfying_assignments() -> None:
    case = check_soundness.Case(Q.hermitian(x + I), Q.imaginary(x), "t1")
    models = check_soundness.find_models(
        case, (x,), (), random.Random("models"), 12, 200)
    assert models
    for model in models:
        assert check_soundness.ground_truth(Q.imaginary(x), model) is True


def test_unsatisfiable_assumptions_are_skipped() -> None:
    case = check_soundness.Case(Q.positive(x), Q.positive(x) & Q.negative(x),
                                "unsat")
    report = _audit(case, _stub(True))
    assert report.findings == ()
    assert not report.has_model


def test_counterexample_is_reported() -> None:
    case = check_soundness.Case(Q.hermitian(x + I), Q.imaginary(x), "t1")
    report = _audit(case, _stub(False))
    assert report.has_model
    assert "counterexample" in [finding.kind for finding in report.findings]


def test_upstream_shared_counterexample_is_suppressed() -> None:
    case = check_soundness.Case(Q.positive(x), True, "positive")

    def ask_fn(proposition: Any, assumptions: Any = True) -> Any:
        return False

    report = _audit(case, _stub(False), ask_fn, use_oracle=True)
    assert report.suppressed == 1
    assert "counterexample" not in [f.kind for f in report.findings]
    strict_report = _audit(
        case, _stub(False), ask_fn, use_oracle=True, strict=True)
    assert "counterexample" in [f.kind for f in strict_report.findings]


def test_spurious_inconsistency_is_reported() -> None:
    case = check_soundness.Case(Q.positive(x), True, "positive")
    report = _audit(
        case, _stub(None, ValueError("Inconsistent assumptions")))
    assert [finding.kind for finding in report.findings] == [
        "spurious-inconsistency"]


def test_both_polars_are_reported() -> None:
    case = check_soundness.Case(Q.positive(x), True, "positive")
    report = _audit(case, _stub(True))
    assert "both-polars" in [finding.kind for finding in report.findings]


def test_oracle_disagreement_is_reported() -> None:
    case = check_soundness.Case(Q.positive(x), True, "positive")

    def ask_fn(proposition: Any, assumptions: Any = True) -> Any:
        return False

    report = _audit(case, _stub(True), ask_fn, use_oracle=True)
    assert "oracle-disagreement" in [finding.kind for finding in report.findings]


def test_sound_stub_reports_nothing() -> None:
    case = check_soundness.Case(Q.positive(x), True, "positive")
    report = _audit(case, _stub(None))
    assert report.findings == ()
    assert report.has_model


def test_hypothesis_cases_carry_satisfying_models() -> None:
    from hypothesis import HealthCheck, given, settings

    @settings(max_examples=15, deadline=None, database=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(check_soundness.hypothesis_cases(True))
    def check(case: Any) -> None:
        assert case.model is not None
        assert check_soundness.ground_truth(case.premises, case.model) is True

    check()


def test_unsoundness_found_carries_findings() -> None:
    case = check_soundness.Case(Q.positive(x), True, "positive")
    finding = check_soundness.Finding("counterexample", case, "detail")
    error = check_soundness.UnsoundnessFound([finding])
    assert error.findings == (finding,)


def test_hypothesis_runner_reports_nothing_for_sound_stub() -> None:
    findings, _ = check_soundness.run_hypothesis(
        _stub(None), None, matrices=False, max_examples=10, use_oracle=False)
    assert findings == []
