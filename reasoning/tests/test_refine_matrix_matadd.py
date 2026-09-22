"""Tests for the ``MatAdd`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.matrices.expressions import MatAdd, MatrixSymbol, ZeroMatrix

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    recording_ask,
    reference_ask,
    stub_ask,
    use_ask,
)

X = MatrixSymbol('X', 2, 2)
Y = MatrixSymbol('Y', 2, 2)
Z = MatrixSymbol('Z', 2, 2)
A = MatrixSymbol('A', 2, 3)
B = MatrixSymbol('B', 2, 3)


def test_drops_zero_term() -> None:
    assert refine(MatAdd(X, Y), Q.zero(Y)) == X
    assert refine(MatAdd(X, Y), Q.zero(X)) == Y


def test_drops_only_zero_terms() -> None:
    assert refine(MatAdd(X, Y, Z), Q.zero(Y)) == X + Z
    assert refine(MatAdd(X, Y, Z), Q.zero(X) & Q.zero(Z)) == Y


def test_all_zero_collapses_to_zero_matrix() -> None:
    assert refine(MatAdd(X, Y), Q.zero(X) & Q.zero(Y)) == ZeroMatrix(2, 2)
    assert refine(MatAdd(A, B), Q.zero(A) & Q.zero(B)) == ZeroMatrix(2, 3)


def test_single_term_sum() -> None:
    # ``MatAdd(X)`` is a one-argument MatAdd, not ``X``.
    assert refine(MatAdd(X), Q.zero(X)) == ZeroMatrix(2, 2)
    assert refine(MatAdd(X), True) == MatAdd(X)


def test_reference_ask_behavior() -> None:
    with reference_ask():
        assert refine(MatAdd(X, Y), Q.zero(Y)) == X
        assert refine(MatAdd(X, Y), Q.zero(X) & Q.zero(Y)) == ZeroMatrix(2, 2)


def test_asks_every_term() -> None:
    fake, log = recording_ask({str(Q.zero(Y)): True})
    with use_ask(fake):
        assert refine(MatAdd(X, Y), Q.zero(Y)) == X
    assert [entry[0] for entry in log] == [Q.zero(X), Q.zero(Y)]


def test_unmet_assumption_unchanged() -> None:
    assert refine(MatAdd(X, Y), Q.diagonal(Y)) == MatAdd(X, Y)
    assert refine(MatAdd(X, Y), Q.zero(Z)) == MatAdd(X, Y)
    assert refine(MatAdd(X, Y), True) == MatAdd(X, Y)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(MatAdd(X, Y), Q.zero(Y)) == MatAdd(X, Y)
        assert refine(MatAdd(X, Y, Z), Q.zero(X) & Q.zero(Y)) == MatAdd(X, Y, Z)
        assert refine(MatAdd(X), Q.zero(X)) == MatAdd(X)
