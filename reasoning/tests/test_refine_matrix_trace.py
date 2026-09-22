"""Tests for the ``Trace`` refine handler."""
from __future__ import annotations

from sympy.abc import x
from sympy.assumptions import Q
from sympy.core import S
from sympy.matrices.expressions import MatrixSymbol, Trace

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    recording_ask,
    reference_ask,
    stub_ask,
    use_ask,
)

X = MatrixSymbol('X', 2, 2)
Y = MatrixSymbol('Y', 2, 2)


def test_zero_matrix_trace() -> None:
    assert refine(Trace(X), Q.zero(X)) == S.Zero


def test_reference_ask_behavior() -> None:
    with reference_ask():
        assert refine(Trace(X), Q.zero(X)) == S.Zero
        assert refine(Trace(X), Q.diagonal(X)) == Trace(X)
        assert refine(Trace(X), True) == Trace(X)


def test_asks_matrix() -> None:
    fake, log = recording_ask({str(Q.zero(X)): True})
    with use_ask(fake):
        assert refine(Trace(X), Q.zero(X)) == S.Zero
    assert [entry[0] for entry in log] == [Q.zero(X)]


def test_unmet_assumption_unchanged() -> None:
    assert refine(Trace(X), Q.diagonal(X)) == Trace(X)
    assert refine(Trace(X), Q.zero(Y)) == Trace(X)
    assert refine(Trace(X), Q.real(x)) == Trace(X)
    assert refine(Trace(X), True) == Trace(X)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(Trace(X), Q.zero(X)) == Trace(X)
