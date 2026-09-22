"""Tests for the extended ``MatrixElement`` refine handler."""
from __future__ import annotations

from sympy.abc import i, j
from sympy.assumptions import Q
from sympy.core import S
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
A = MatrixSymbol('A', 3, 3)


def test_reference_ask_fidelity() -> None:
    assert_refines_like_sympy(X[1, 0], Q.symmetric(X))
    assert_refines_like_sympy(X[0, 1], Q.symmetric(X))
    assert_refines_like_sympy(X[1, 0], Q.symmetric(Y))
    assert_refines_like_sympy(X[0, 1], True)
    assert_refines_like_sympy(A[i, i], Q.diagonal(A))


def test_zero_matrix_element() -> None:
    assert refine(X[0, 1], Q.zero(X)) == S.Zero
    assert refine(X[1, 0], Q.zero(X)) == S.Zero
    assert refine(X[0, 0], Q.zero(X)) == S.Zero


def test_diagonal_element_with_distinct_literals() -> None:
    assert refine(X[0, 1], Q.diagonal(X)) == S.Zero
    assert refine(X[1, 0], Q.diagonal(X)) == S.Zero
    assert refine(A[0, 2], Q.diagonal(A)) == S.Zero
    assert refine(A[2, 0], Q.diagonal(A)) == S.Zero


def test_diagonal_element_with_offset_symbols() -> None:
    assert refine(A[i, i + 1], Q.diagonal(A)) == S.Zero
    assert refine(A[i + 1, i], Q.diagonal(A)) == S.Zero
    assert refine(A[i, i - 1], Q.diagonal(A)) == S.Zero


def test_diagonal_element_with_independent_symbols() -> None:
    # Independent symbols may be equal, so no zero is provable; only the
    # vendored symmetric-index swap applies.
    assert refine(A[i, j], Q.diagonal(A)) == A[j, i]
    assert refine(A[j, i], Q.diagonal(A)) == A[j, i]
    assert refine(A[i, 2 * i], Q.diagonal(A)) == A[i, 2 * i]
    assert refine(A[i, j], Q.diagonal(A) & Q.ne(i, j)) == S.Zero


def test_symmetric_index_swap_kept() -> None:
    assert refine(X[1, 0], Q.symmetric(X)) == X[0, 1]
    assert refine(X[0, 1], Q.symmetric(X)) == X[0, 1]


def test_ask_order() -> None:
    fake, log = recording_ask({str(Q.zero(X)): True})
    with use_ask(fake):
        assert refine(X[0, 1], Q.zero(X)) == S.Zero
    assert [entry[0] for entry in log] == [Q.zero(X)]

    fake, log = recording_ask({str(Q.diagonal(X)): True})
    with use_ask(fake):
        assert refine(X[0, 1], Q.diagonal(X)) == S.Zero
    assert [entry[0] for entry in log] == [Q.zero(X), Q.diagonal(X)]

    fake, log = recording_ask({str(Q.symmetric(X)): True})
    with use_ask(fake):
        assert refine(X[1, 0], Q.symmetric(X)) == X[0, 1]
    assert [entry[0] for entry in log] == [
        Q.zero(X), Q.diagonal(X), Q.symmetric(X),
        Q.zero(X), Q.diagonal(X), Q.symmetric(X),
    ]


def test_unmet_assumption_unchanged() -> None:
    assert refine(X[0, 1], Q.diagonal(Y)) == X[0, 1]
    assert refine(X[0, 0], Q.diagonal(X)) == X[0, 0]
    assert refine(X[1, 1], Q.diagonal(X)) == X[1, 1]
    assert refine(A[i, i], Q.diagonal(A)) == A[i, i]
    # A mixed literal/symbolic pair is not provably distinct: ``A[0, i]`` is
    # on the diagonal when ``i`` is zero.
    assert refine(A[0, i], Q.diagonal(A)) == A[0, i]
    assert refine(A[1, i], Q.diagonal(A)) == A[1, i]
    assert refine(X[0, 1], Q.symmetric(X)) == X[0, 1]
    assert refine(X[0, 1], True) == X[0, 1]


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(X[0, 1], Q.zero(X)) == X[0, 1]
        assert refine(X[0, 1], Q.diagonal(X)) == X[0, 1]
        assert refine(X[1, 0], Q.symmetric(X)) == X[1, 0]
        assert refine(A[j, i], Q.diagonal(A)) == A[j, i]
