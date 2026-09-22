"""Tests for the ``sec`` and ``csc`` refine handlers."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import m, n, x
from sympy.core import S
from sympy.core.numbers import zoo
from sympy.functions.elementary.trigonometric import csc, sec

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    stub_ask,
    use_ask,
)


ODD_VALUES = [S.One, S.NegativeOne, S(3), S(-3)]


def test_sec_integer_multiple_of_pi() -> None:
    assert refine(sec(n * S.Pi), Q.integer(n)) == (-1) ** n
    assert refine(sec(n * S.Pi), Q.even(n)) == 1
    assert refine(sec(n * S.Pi), Q.odd(n)) == -1
    assert_refinement_valid(sec(n * S.Pi), Q.integer(n), (-1) ** n)


def test_sec_odd_half_pi_shift() -> None:
    assert refine(sec(x + n * S.Pi / 2), Q.odd(n)) == \
        (-1) ** ((n + 1) / 2) * csc(x)
    assert_refinement_valid(
        sec(x + n * S.Pi / 2),
        Q.odd(n),
        (-1) ** ((n + 1) / 2) * csc(x),
        values={n: ODD_VALUES},
    )


def test_sec_odd_half_pi_multiple_is_pole() -> None:
    assert refine(sec(n * S.Pi / 2), Q.odd(n)) is zoo
    assert refine(sec(n * S.Pi / 2), Q.even(n)) == (-1) ** (n / 2)


def test_csc_integer_multiple_of_pi_is_pole() -> None:
    assert refine(csc(n * S.Pi), Q.integer(n)) is zoo
    assert_refinement_valid(csc(n * S.Pi), Q.integer(n), zoo)


def test_csc_odd_half_pi_multiple_parity() -> None:
    assert refine(csc(n * S.Pi / 2), Q.odd(n)) == (-1) ** ((n + 3) / 2)
    assert refine(
        csc(n * S.Pi / 2), Q.odd(n) & Q.even((n - 1) / 2)
    ) == 1
    assert refine(
        csc(n * S.Pi / 2), Q.odd(n) & Q.odd((n - 1) / 2)
    ) == -1
    assert refine(csc(n * S.Pi / 2), Q.even(n)) is zoo


def test_csc_odd_half_pi_shift() -> None:
    assert refine(csc(x + n * S.Pi / 2), Q.odd(n)) == \
        (-1) ** ((n + 3) / 2) * sec(x)
    assert_refinement_valid(
        csc(x + n * S.Pi / 2),
        Q.odd(n),
        (-1) ** ((n + 3) / 2) * sec(x),
        values={n: ODD_VALUES},
    )


def test_zero_argument() -> None:
    assert refine(sec(x), Q.zero(x)) == 1
    assert refine(csc(x), Q.zero(x)) is zoo


def test_no_refinement_without_assumptions() -> None:
    assert refine(sec(n * S.Pi), Q.real(n)) == sec(n * S.Pi)
    assert refine(csc(n * S.Pi), Q.real(n)) == csc(n * S.Pi)
    assert refine(sec(x), Q.nonzero(x)) == sec(x)
    assert refine(csc(x), Q.nonzero(x)) == csc(x)


def test_no_refinement_for_unknown_parity() -> None:
    assert refine(sec(n * S.Pi / 2), Q.integer(n)) == sec(n * S.Pi / 2)
    assert refine(csc(n * S.Pi / 2), Q.integer(n)) == csc(n * S.Pi / 2)
    assert refine(sec(x + n * S.Pi / 2), Q.integer(n)) == \
        sec(x + n * S.Pi / 2)
    assert refine(csc(x + n * S.Pi / 2), Q.integer(n)) == \
        csc(x + n * S.Pi / 2)


def test_none_safe() -> None:
    with use_ask(stub_ask({})):
        assert refine(sec(x), Q.zero(x)) == sec(x)
        assert refine(csc(x), Q.zero(x)) == csc(x)
        assert refine(sec(n * S.Pi), Q.integer(n)) == sec(n * S.Pi)
        assert refine(csc(n * S.Pi), Q.integer(n)) == csc(n * S.Pi)
        assert refine(sec(x + n * S.Pi / 2), Q.odd(n)) == \
            sec(x + n * S.Pi / 2)
        assert refine(csc(x + n * S.Pi / 2), Q.odd(n)) == \
            csc(x + n * S.Pi / 2)


def test_integration_structural_parity() -> None:
    assert refine(sec(x + 2 * n * S.Pi), Q.integer(n)) == sec(x)
    assert refine(csc(x + 2 * n * S.Pi), Q.integer(n)) == csc(x)
    assert refine(sec((2 * n + 1) * S.Pi), Q.integer(n)) == -1
    assert refine(csc((2 * n + 1) * S.Pi), Q.integer(n)) is zoo
    assert refine(sec(x + (2 * n + 1) * S.Pi / 2), Q.integer(n)) == \
        (-1) ** (n + 1) * csc(x)
    assert refine(csc(x + (2 * n + 1) * S.Pi / 2), Q.integer(n)) == \
        (-1) ** n * sec(x)
    assert refine(
        sec(x + n * S.Pi + m * S.Pi / 2), Q.integer(n) & Q.integer(m)
    ) == (-1) ** n * sec(x + m * S.Pi / 2)
    assert refine(
        csc(x + n * S.Pi + m * S.Pi / 2), Q.integer(n) & Q.integer(m)
    ) == (-1) ** n * csc(x + m * S.Pi / 2)
    assert refine(
        sec(x + n * S.Pi + m * S.Pi / 2), Q.integer(n) & Q.odd(m)
    ) == (-1) ** (n + (m + 1) / 2) * csc(x)
