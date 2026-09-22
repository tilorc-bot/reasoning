"""Tests for the ``RisingFactorial`` and ``FallingFactorial`` refine handlers."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import k, n, x
from sympy.core import S
from sympy.functions.combinatorial.factorials import (
    FallingFactorial,
    RisingFactorial,
    factorial,
)

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    recording_ask,
    stub_ask,
    use_ask,
)

INTEGERS = [-4, -3, -2, -1, 1, 2, 3, 4]


def test_zero_k_is_one() -> None:
    assert refine(RisingFactorial(x, k), Q.zero(k)) is S.One
    assert refine(FallingFactorial(x, k), Q.zero(k)) is S.One


def test_zero_base_with_positive_integer_k_is_zero() -> None:
    assumptions = Q.zero(x) & Q.integer(k) & Q.positive(k)
    assert refine(RisingFactorial(x, k), assumptions) is S.Zero
    assert refine(FallingFactorial(x, k), assumptions) is S.Zero


def test_falling_factorial_with_equal_integer_arguments() -> None:
    assert refine(FallingFactorial(n, n), Q.integer(n)) == factorial(n)


def test_unmet_assumptions_unchanged() -> None:
    assert refine(RisingFactorial(x, k), Q.real(x) & Q.real(k)) == RisingFactorial(x, k)
    assert refine(FallingFactorial(x, k), Q.real(x) & Q.real(k)) == FallingFactorial(x, k)
    assert refine(RisingFactorial(x, k), Q.zero(x)) == RisingFactorial(x, k)
    assert refine(FallingFactorial(x, k), Q.zero(x)) == FallingFactorial(x, k)
    assert refine(
        RisingFactorial(x, k), Q.zero(x) & Q.negative(k)
    ) == RisingFactorial(x, k)
    assert refine(FallingFactorial(n, n), Q.real(n)) == FallingFactorial(n, n)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(RisingFactorial(x, k), Q.zero(k)) == RisingFactorial(x, k)
        assert refine(FallingFactorial(x, k), Q.zero(k)) == FallingFactorial(x, k)
        assert refine(
            RisingFactorial(x, k), Q.zero(x) & Q.integer(k) & Q.positive(k)
        ) == RisingFactorial(x, k)
        assert refine(FallingFactorial(n, n), Q.integer(n)) == FallingFactorial(n, n)


def test_numeric_oracle() -> None:
    assert_refinement_valid(RisingFactorial(x, k), Q.zero(k), S.One)
    assert_refinement_valid(FallingFactorial(x, k), Q.zero(k), S.One)
    zero_base = Q.zero(x) & Q.integer(k) & Q.positive(k)
    assert_refinement_valid(
        RisingFactorial(x, k), zero_base, S.Zero, values={x: [0], k: INTEGERS}
    )
    assert_refinement_valid(
        FallingFactorial(x, k), zero_base, S.Zero, values={x: [0], k: INTEGERS}
    )
    assert_refinement_valid(
        FallingFactorial(n, n), Q.integer(n), factorial(n), values={n: INTEGERS}
    )


def test_returns_factorial_instance() -> None:
    refined = refine(FallingFactorial(n, n), Q.integer(n))
    assert isinstance(refined, factorial)
    assert refined == factorial(n)


def test_ask_goes_through_upstream() -> None:
    fake, log = recording_ask({str(Q.zero(k)): True})
    with use_ask(fake):
        assert refine(RisingFactorial(x, k), Q.zero(k)) is S.One
    assert [entry[0] for entry in log] == [Q.zero(k)]
