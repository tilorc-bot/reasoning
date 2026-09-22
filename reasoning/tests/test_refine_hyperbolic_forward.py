"""Tests for the forward hyperbolic refine handlers."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import m, n, x
from sympy.core import S
from sympy.core.numbers import zoo
from sympy.functions.elementary.hyperbolic import (
    cosh,
    coth,
    csch,
    sech,
    sinh,
    tanh,
)

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    stub_ask,
    use_ask,
)


I_PI = S.ImaginaryUnit * S.Pi

ODD_VALUES = [S.One, S.NegativeOne, S(3), S(-3)]
EVEN_VALUES = [S.Zero, S(2), S(-2), S(4)]


def test_zero_argument_limiting_values() -> None:
    assert refine(sinh(x), Q.zero(x)) == S.Zero
    assert refine(cosh(x), Q.zero(x)) == S.One
    assert refine(tanh(x), Q.zero(x)) == S.Zero
    assert refine(coth(x), Q.zero(x)) is zoo
    assert refine(sech(x), Q.zero(x)) == S.One
    assert refine(csch(x), Q.zero(x)) is zoo


def test_zero_argument_numeric_oracle() -> None:
    assert_refinement_valid(sinh(x), Q.zero(x), S.Zero)
    assert_refinement_valid(cosh(x), Q.zero(x), S.One)
    assert_refinement_valid(tanh(x), Q.zero(x), S.Zero)
    assert_refinement_valid(coth(x), Q.zero(x), zoo)
    assert_refinement_valid(sech(x), Q.zero(x), S.One)
    assert_refinement_valid(csch(x), Q.zero(x), zoo)


def test_sinh_cosh_parity_shift() -> None:
    assert refine(sinh(x + n * I_PI), Q.even(n)) == sinh(x)
    assert refine(sinh(x + n * I_PI), Q.odd(n)) == -sinh(x)
    assert refine(cosh(x + n * I_PI), Q.even(n)) == cosh(x)
    assert refine(cosh(x + n * I_PI), Q.odd(n)) == -cosh(x)
    assert_refinement_valid(
        sinh(x + n * I_PI), Q.odd(n), -sinh(x), values={n: ODD_VALUES}
    )
    assert_refinement_valid(
        cosh(x + n * I_PI), Q.odd(n), -cosh(x), values={n: ODD_VALUES}
    )


def test_sech_csch_parity_shift() -> None:
    assert refine(sech(x + n * I_PI), Q.even(n)) == sech(x)
    assert refine(sech(x + n * I_PI), Q.odd(n)) == -sech(x)
    assert refine(csch(x + n * I_PI), Q.even(n)) == csch(x)
    assert refine(csch(x + n * I_PI), Q.odd(n)) == -csch(x)
    assert_refinement_valid(
        sech(x + n * I_PI), Q.odd(n), -sech(x), values={n: ODD_VALUES}
    )
    assert_refinement_valid(
        csch(x + n * I_PI), Q.odd(n), -csch(x), values={n: ODD_VALUES}
    )


def test_tanh_coth_are_pi_i_periodic() -> None:
    assert refine(tanh(x + n * I_PI), Q.integer(n)) == tanh(x)
    assert refine(coth(x + n * I_PI), Q.integer(n)) == coth(x)
    assert_refinement_valid(tanh(x + n * I_PI), Q.integer(n), tanh(x))
    assert_refinement_valid(coth(x + n * I_PI), Q.integer(n), coth(x))


def test_tanh_poles_and_zeros() -> None:
    assert refine(tanh(n * I_PI / 2), Q.odd(n)) is zoo
    assert refine(tanh((n + m + S.Half) * I_PI),
                  Q.integer(n) & Q.integer(m)) is zoo
    assert refine(tanh(n * I_PI), Q.integer(n)) == S.Zero
    assert_refinement_valid(
        tanh(n * I_PI / 2), Q.odd(n), zoo, values={n: ODD_VALUES}
    )
    assert_refinement_valid(
        tanh((n + m + S.Half) * I_PI), Q.integer(n) & Q.integer(m), zoo
    )


def test_coth_poles_and_zeros() -> None:
    assert refine(coth(n * I_PI), Q.integer(n)) is zoo
    assert refine(coth(n * I_PI / 2), Q.odd(n)) == S.Zero
    assert refine(coth((n + m + S.Half) * I_PI),
                  Q.integer(n) & Q.integer(m)) == S.Zero
    assert_refinement_valid(coth(n * I_PI), Q.integer(n), zoo)
    assert_refinement_valid(
        coth(n * I_PI / 2), Q.odd(n), S.Zero, values={n: ODD_VALUES}
    )


def test_no_refinement_for_nonzero_argument() -> None:
    assert refine(sinh(x), Q.nonzero(x)) == sinh(x)
    assert refine(cosh(x), Q.real(x)) == cosh(x)
    assert refine(tanh(x), Q.nonzero(x)) == tanh(x)
    assert refine(coth(x), Q.real(x)) == coth(x)
    assert refine(sech(x), Q.nonzero(x)) == sech(x)
    assert refine(csch(x), Q.real(x)) == csch(x)


def test_no_refinement_for_unknown_integer_shift() -> None:
    assert refine(sinh(x + n * I_PI), Q.real(n)) == sinh(x + n * I_PI)
    assert refine(cosh(x + n * I_PI), Q.real(n)) == cosh(x + n * I_PI)
    assert refine(tanh(x + n * I_PI), Q.real(n)) == tanh(x + n * I_PI)
    assert refine(coth(x + n * I_PI), Q.real(n)) == coth(x + n * I_PI)


def test_no_refinement_for_unknown_parity() -> None:
    assert refine(sinh(x + n * I_PI), Q.integer(n)) == sinh(x + n * I_PI)
    assert refine(cosh(x + n * I_PI), Q.integer(n)) == cosh(x + n * I_PI)
    assert refine(sech(x + n * I_PI), Q.integer(n)) == sech(x + n * I_PI)
    assert refine(csch(x + n * I_PI), Q.integer(n)) == csch(x + n * I_PI)
    assert refine(tanh(n * I_PI / 2), Q.integer(n)) == tanh(n * I_PI / 2)


def test_integration_additive_shifts() -> None:
    assert refine(sinh(x + 2 * n * I_PI), Q.integer(n)) == sinh(x)
    assert refine(sinh(x + (2 * n + 1) * I_PI), Q.integer(n)) == -sinh(x)
    assert refine(cosh(x + 2 * n * I_PI), Q.integer(n)) == cosh(x)
    assert refine(cosh(x + (2 * n + 1) * I_PI), Q.integer(n)) == -cosh(x)
    assert refine(
        tanh(x + n * I_PI + m * I_PI), Q.integer(n) & Q.integer(m)
    ) == tanh(x)
    assert refine(
        sinh(x + n * I_PI + m * I_PI), Q.odd(n) & Q.even(m)
    ) == -sinh(x)
    assert refine(
        sinh(x + n * I_PI + m * I_PI), Q.even(n) & Q.even(m)
    ) == sinh(x)
    assert_refinement_valid(
        sinh(x + n * I_PI + m * I_PI),
        Q.odd(n) & Q.even(m),
        -sinh(x),
        values={n: ODD_VALUES, m: EVEN_VALUES},
    )


def test_none_answers_leave_expression_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(sinh(x), Q.zero(x)) == sinh(x)
        assert refine(cosh(x), Q.zero(x)) == cosh(x)
        assert refine(tanh(x), Q.zero(x)) == tanh(x)
        assert refine(coth(x), Q.zero(x)) == coth(x)
        assert refine(sech(x), Q.zero(x)) == sech(x)
        assert refine(csch(x), Q.zero(x)) == csch(x)
        assert refine(sinh(x + n * I_PI), Q.odd(n)) == sinh(x + n * I_PI)
        assert refine(cosh(x + n * I_PI), Q.even(n)) == cosh(x + n * I_PI)
        assert refine(tanh(x + n * I_PI), Q.integer(n)) == tanh(x + n * I_PI)
        assert refine(tanh(n * I_PI / 2), Q.odd(n)) == tanh(n * I_PI / 2)
        assert refine(coth(n * I_PI), Q.integer(n)) == coth(n * I_PI)
