"""Tests for the ``HadamardProduct`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.matrices.expressions import HadamardProduct, MatrixSymbol, ZeroMatrix

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


def test_zero_factor_collapses() -> None:
    assert refine(HadamardProduct(X, Y), Q.zero(Y)) == ZeroMatrix(2, 2)
    assert refine(HadamardProduct(X, Y), Q.zero(X)) == ZeroMatrix(2, 2)
    assert refine(HadamardProduct(X, Y, Z), Q.zero(Z)) == ZeroMatrix(2, 2)


def test_rectangular_shape() -> None:
    assert refine(HadamardProduct(A, B), Q.zero(B)) == ZeroMatrix(2, 3)


def test_reference_ask_behavior() -> None:
    with reference_ask():
        assert refine(HadamardProduct(X, Y), Q.zero(Y)) == ZeroMatrix(2, 2)
        assert refine(HadamardProduct(X, Y), True) == HadamardProduct(X, Y)


def test_asks_every_factor() -> None:
    fake, log = recording_ask({str(Q.zero(Y)): True})
    with use_ask(fake):
        assert refine(HadamardProduct(X, Y), Q.zero(Y)) == ZeroMatrix(2, 2)
    assert [entry[0] for entry in log] == [Q.zero(X), Q.zero(Y)]


def test_unmet_assumption_unchanged() -> None:
    assert refine(HadamardProduct(X, Y), Q.diagonal(Y)) == HadamardProduct(X, Y)
    assert refine(HadamardProduct(X, Y), Q.zero(Z)) == HadamardProduct(X, Y)
    assert refine(HadamardProduct(X, Y), True) == HadamardProduct(X, Y)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(HadamardProduct(X, Y), Q.zero(Y)) == HadamardProduct(X, Y)
        assert refine(HadamardProduct(A, B), Q.zero(A)) == HadamardProduct(A, B)
