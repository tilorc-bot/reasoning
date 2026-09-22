"""Tests for the ``Determinant`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x
from sympy.core import S
from sympy.matrices.expressions import MatrixSymbol
from sympy.matrices.expressions.determinant import det

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refines_like_sympy,
    recording_ask,
    stub_ask,
    use_ask,
)

X = MatrixSymbol('X', 2, 2)


def test_reference_ask_fidelity() -> None:
    assert_refines_like_sympy(det(X), Q.orthogonal(X))
    assert_refines_like_sympy(det(X), Q.singular(X))
    assert_refines_like_sympy(det(X), Q.unit_triangular(X))
    assert_refines_like_sympy(det(X), Q.symmetric(X))
    assert_refines_like_sympy(det(X), True)


def test_local_refinement() -> None:
    assert refine(det(X), Q.orthogonal(X)) == S.One
    assert refine(det(X), Q.singular(X)) == S.Zero
    assert refine(det(X), Q.unit_triangular(X)) == S.One


def test_asks_base_matrix() -> None:
    fake, log = recording_ask({str(Q.orthogonal(X)): True})
    with use_ask(fake):
        assert refine(det(X), Q.orthogonal(X)) == S.One
    assert [entry[0] for entry in log] == [Q.orthogonal(X)]


def test_singular_ask_order() -> None:
    fake, log = recording_ask({str(Q.singular(X)): True})
    with use_ask(fake):
        assert refine(det(X), Q.singular(X)) == S.Zero
    assert [entry[0] for entry in log] == [Q.orthogonal(X), Q.singular(X)]


def test_unit_triangular_ask_order() -> None:
    fake, log = recording_ask({str(Q.unit_triangular(X)): True})
    with use_ask(fake):
        assert refine(det(X), Q.unit_triangular(X)) == S.One
    assert [entry[0] for entry in log] == [
        Q.orthogonal(X),
        Q.singular(X),
        Q.unit_triangular(X),
    ]


def test_unmet_assumption_unchanged() -> None:
    assert refine(det(X), Q.symmetric(X)) == det(X)
    assert refine(det(X), Q.real(x)) == det(X)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(det(X), Q.orthogonal(X)) == det(X)
        assert refine(det(X), Q.singular(X)) == det(X)
        assert refine(det(X), Q.unit_triangular(X)) == det(X)
