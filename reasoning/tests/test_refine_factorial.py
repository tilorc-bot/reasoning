"""Tests for the ``factorial`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import n
from sympy.core import S
from sympy.functions.combinatorial.factorials import factorial
from sympy.functions.special.gamma_functions import gamma

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    recording_ask,
    stub_ask,
    use_ask,
)


def test_zero_argument_is_one() -> None:
    assert refine(factorial(n), Q.zero(n)) is S.One


def test_one_argument_is_one() -> None:
    assert refine(factorial(n), Q.eq(n, 1)) is S.One


def test_negative_integer_is_pole() -> None:
    assert refine(factorial(n), Q.integer(n) & Q.negative(n)) is S.ComplexInfinity


def test_positive_infinite_is_infinity() -> None:
    assert refine(factorial(n), Q.positive_infinite(n)) is S.Infinity


def test_negative_infinite_is_gamma_pole() -> None:
    assert refine(factorial(n), Q.negative_infinite(n)) == gamma(S.NegativeInfinity)


def test_unmet_assumptions_unchanged() -> None:
    assert refine(factorial(n), Q.real(n)) == factorial(n)
    assert refine(factorial(n), Q.integer(n)) == factorial(n)
    assert refine(factorial(n), Q.positive(n)) == factorial(n)
    assert refine(factorial(n), Q.negative(n)) == factorial(n)
    assert refine(factorial(n), Q.infinite(n)) == factorial(n)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(factorial(n), Q.zero(n)) == factorial(n)
        assert refine(factorial(n), Q.integer(n) & Q.negative(n)) == factorial(n)
        assert refine(factorial(n), Q.positive_infinite(n)) == factorial(n)
        assert refine(factorial(n), Q.negative_infinite(n)) == factorial(n)


def test_numeric_oracle() -> None:
    assert_refinement_valid(factorial(n), Q.zero(n), S.One)
    assert_refinement_valid(factorial(n), Q.eq(n, 1), S.One)
    assert_refinement_valid(
        factorial(n),
        Q.integer(n) & Q.negative(n),
        S.ComplexInfinity,
        values={n: [-4, -3, -2, -1]},
    )
    assert_refinement_valid(
        factorial(n),
        Q.positive_infinite(n),
        S.Infinity,
        values={n: [S.Infinity]},
    )
    assert_refinement_valid(
        factorial(n),
        Q.negative_infinite(n),
        gamma(S.NegativeInfinity),
        values={n: [S.NegativeInfinity]},
    )


def test_ask_goes_through_upstream() -> None:
    fake, log = recording_ask({str(Q.zero(n)): True})
    with use_ask(fake):
        assert refine(factorial(n), Q.zero(n)) is S.One
    assert [entry[0] for entry in log] == [Q.zero(n)]
