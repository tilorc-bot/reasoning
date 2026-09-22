"""Tests for the ``MatMul`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x
from sympy.matrices.expressions import Identity, MatMul, MatrixSymbol

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
    assert_refines_like_sympy(X.T * X, Q.orthogonal(X))
    assert_refines_like_sympy(X.conjugate() * X, Q.unitary(X))
    assert_refines_like_sympy(X.T * Y, Q.orthogonal(X) & Q.orthogonal(Y))
    assert_refines_like_sympy(X.T * X, True)


def test_local_refinement() -> None:
    # Upstream returns the one-factor ``MatMul(Identity(2))`` wrapper (it
    # does not auto-collapse in this SymPy pin); ``doit`` reaches ``I``.
    assert refine(X.T * X, Q.orthogonal(X)) == MatMul(Identity(2))
    assert refine(X.T * X, Q.orthogonal(X)).doit() == Identity(2)
    assert refine(X.conjugate() * X, Q.unitary(X)) == MatMul(Identity(2))
    assert refine(X.conjugate() * X, Q.unitary(X)).doit() == Identity(2)


def test_scalar_factor_preserved() -> None:
    assert refine(2 * X.T * X, Q.orthogonal(X)) == 2 * Identity(2)


def test_asks_factor() -> None:
    fake, log = recording_ask({
        str(Q.symmetric(X)): None,
        str(Q.orthogonal(X)): True,
    })
    with use_ask(fake):
        assert refine(X.T * X, Q.orthogonal(X)) == MatMul(Identity(2))
    assert Q.orthogonal(X) in [entry[0] for entry in log]


def test_non_cancelling_product_unchanged() -> None:
    assert refine(X.T * Y, Q.orthogonal(X) & Q.orthogonal(Y)) == X.T * Y


def test_unmet_assumption_unchanged() -> None:
    assert refine(X.T * X, Q.unitary(X)) == X.T * X
    assert refine(X.T * X, Q.real(x)) == X.T * X


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(X.T * X, Q.orthogonal(X)) == X.T * X
        assert refine(X.conjugate() * X, Q.unitary(X)) == X.conjugate() * X
