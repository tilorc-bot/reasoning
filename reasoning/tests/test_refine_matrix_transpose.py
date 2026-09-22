"""Tests for the ``Transpose`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x
from sympy.matrices.expressions import MatrixSymbol

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refines_like_sympy,
    recording_ask,
    stub_ask,
    use_ask,
)

X = MatrixSymbol('X', 2, 2)
Y = MatrixSymbol('Y', 2, 2)


def test_reference_ask_fidelity() -> None:
    assert_refines_like_sympy(X.T, Q.symmetric(X))
    assert_refines_like_sympy(X.T, Q.orthogonal(X))
    assert_refines_like_sympy(X.T, Q.symmetric(Y))
    assert_refines_like_sympy(X.T, True)


def test_local_refinement() -> None:
    assert refine(X.T, Q.symmetric(X)) == X


def test_asks_base_matrix() -> None:
    fake, log = recording_ask({str(Q.symmetric(X)): True})
    with use_ask(fake):
        assert refine(X.T, Q.symmetric(X)) == X
    assert [entry[0] for entry in log] == [Q.symmetric(X)]


def test_unmet_assumption_unchanged() -> None:
    assert refine(X.T, Q.orthogonal(X)) == X.T
    assert refine(X.T, Q.symmetric(Y)) == X.T
    assert refine(X.T, Q.real(x)) == X.T


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(X.T, Q.symmetric(X)) == X.T
