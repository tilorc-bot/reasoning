"""Tests for the ``tan`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import m, n, x
from sympy.core import S
from sympy.core.numbers import zoo
from sympy.functions.elementary.trigonometric import cot, tan

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    stub_ask,
    use_ask,
)


ODD_VALUES = [S.One, S.NegativeOne, S(3), S(-3)]


def test_zero_argument() -> None:
    assert refine(tan(x), Q.zero(x)) == 0
    assert_refinement_valid(tan(x), Q.zero(x), 0)


def test_integer_multiple_of_pi() -> None:
    assert refine(tan(n * S.Pi), Q.integer(n)) == 0
    assert_refinement_valid(tan(n * S.Pi), Q.integer(n), 0)


def test_integer_pi_shift() -> None:
    assert refine(tan(x + n * S.Pi), Q.integer(n)) == tan(x)
    assert_refinement_valid(tan(x + n * S.Pi), Q.integer(n), tan(x))


def test_odd_half_pi_multiple_is_pole() -> None:
    assert refine(tan(n * S.Pi / 2), Q.odd(n)) is zoo


def test_odd_half_pi_shift() -> None:
    assert refine(tan(x + n * S.Pi / 2), Q.odd(n)) == -cot(x)
    assert_refinement_valid(
        tan(x + n * S.Pi / 2), Q.odd(n), -cot(x), values={n: ODD_VALUES}
    )


def test_even_half_pi_shift() -> None:
    assert refine(tan(x + n * S.Pi / 2), Q.even(n)) == tan(x)


def test_no_refinement_without_zero_assumption() -> None:
    assert refine(tan(x), Q.nonzero(x)) == tan(x)
    assert refine(tan(x), Q.real(x)) == tan(x)


def test_no_refinement_for_unknown_integer() -> None:
    assert refine(tan(n * S.Pi), Q.real(n)) == tan(n * S.Pi)
    assert refine(tan(x + n * S.Pi), Q.real(n)) == tan(x + n * S.Pi)


def test_no_refinement_for_unknown_parity() -> None:
    assert refine(tan(n * S.Pi / 2), Q.integer(n)) == tan(n * S.Pi / 2)
    assert refine(tan(x + n * S.Pi / 2), Q.integer(n)) == tan(x + n * S.Pi / 2)


def test_none_safe() -> None:
    with use_ask(stub_ask({})):
        assert refine(tan(x), Q.zero(x)) == tan(x)
        assert refine(tan(n * S.Pi), Q.integer(n)) == tan(n * S.Pi)
        assert refine(tan(x + n * S.Pi / 2), Q.odd(n)) == tan(x + n * S.Pi / 2)


def test_integration_structural_parity() -> None:
    assert refine(tan((2 * n + 1) * S.Pi), Q.integer(n)) == 0
    assert refine(tan(x + 2 * n * S.Pi), Q.integer(n)) == tan(x)
    assert refine(tan(x + (2 * n + 1) * S.Pi / 2), Q.integer(n)) == -cot(x)
    assert refine(
        tan(x + n * S.Pi + m * S.Pi / 2), Q.integer(n) & Q.integer(m)
    ) == tan(x + m * S.Pi / 2)
    assert refine(
        tan(x + n * S.Pi + m * S.Pi / 2), Q.integer(n) & Q.odd(m)
    ) == -cot(x)
