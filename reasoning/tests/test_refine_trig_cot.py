"""Tests for the ``cot`` refine handler."""
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
    assert refine(cot(x), Q.zero(x)) is zoo
    assert_refinement_valid(cot(x), Q.zero(x), zoo)


def test_odd_half_pi_multiple() -> None:
    assert refine(cot(n * S.Pi / 2), Q.odd(n)) == 0
    assert_refinement_valid(
        cot(n * S.Pi / 2), Q.odd(n), 0, values={n: ODD_VALUES}
    )


def test_integer_pi_shift() -> None:
    assert refine(cot(x + n * S.Pi), Q.integer(n)) == cot(x)
    assert_refinement_valid(cot(x + n * S.Pi), Q.integer(n), cot(x))


def test_odd_half_pi_shift() -> None:
    assert refine(cot(x + n * S.Pi / 2), Q.odd(n)) == -tan(x)
    assert_refinement_valid(
        cot(x + n * S.Pi / 2), Q.odd(n), -tan(x), values={n: ODD_VALUES}
    )


def test_even_half_pi_shift() -> None:
    assert refine(cot(x + n * S.Pi / 2), Q.even(n)) == cot(x)


def test_no_refinement_without_zero_assumption() -> None:
    assert refine(cot(x), Q.nonzero(x)) == cot(x)
    assert refine(cot(x), Q.real(x)) == cot(x)


def test_no_refinement_for_unknown_integer() -> None:
    assert refine(cot(x + n * S.Pi), Q.real(n)) == cot(x + n * S.Pi)
    assert refine(cot(n * S.Pi), Q.real(n)) == cot(n * S.Pi)


def test_no_refinement_for_unknown_parity() -> None:
    assert refine(cot(n * S.Pi / 2), Q.integer(n)) == cot(n * S.Pi / 2)
    assert refine(cot(x + n * S.Pi / 2), Q.integer(n)) == cot(x + n * S.Pi / 2)


def test_none_safe() -> None:
    with use_ask(stub_ask({})):
        assert refine(cot(x), Q.zero(x)) == cot(x)
        assert refine(cot(n * S.Pi / 2), Q.odd(n)) == cot(n * S.Pi / 2)
        assert refine(cot(x + n * S.Pi), Q.integer(n)) == cot(x + n * S.Pi)


def test_integration_structural_parity() -> None:
    assert refine(cot(n * S.Pi), Q.integer(n)) is zoo
    assert refine(cot(x + 2 * n * S.Pi), Q.integer(n)) == cot(x)
    assert refine(cot(x + (2 * n + 1) * S.Pi / 2), Q.integer(n)) == -tan(x)
    assert refine(
        cot(x + n * S.Pi + m * S.Pi / 2), Q.integer(n) & Q.integer(m)
    ) == cot(x + m * S.Pi / 2)
    assert refine(
        cot(x + n * S.Pi + m * S.Pi / 2), Q.integer(n) & Q.odd(m)
    ) == -tan(x)
