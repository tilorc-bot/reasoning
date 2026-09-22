"""Tests for the inverse hyperbolic refine handlers."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x
from sympy.core import S
from sympy.core.numbers import Rational
from sympy.functions.elementary.hyperbolic import (
    acosh,
    acoth,
    acsch,
    asech,
    asinh,
    atanh,
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


NONZERO_REAL_VALUES = [
    S.One,
    S.NegativeOne,
    S.Half,
    Rational(-1, 2),
    S(2),
    S(-2),
    S(3),
]


def test_asinh_sinh_real() -> None:
    assert refine(asinh(sinh(x)), Q.real(x)) == x
    assert_refinement_valid(asinh(sinh(x)), Q.real(x), x)


def test_asinh_sinh_not_real() -> None:
    assert refine(asinh(sinh(x)), Q.imaginary(x)) == asinh(sinh(x))
    assert refine(asinh(sinh(x)), True) == asinh(sinh(x))


def test_acosh_cosh_nonnegative() -> None:
    assert refine(acosh(cosh(x)), Q.nonnegative(x)) == x
    assert_refinement_valid(acosh(cosh(x)), Q.nonnegative(x), x)


def test_acosh_cosh_not_nonnegative() -> None:
    assert refine(acosh(cosh(x)), Q.real(x)) == acosh(cosh(x))
    assert refine(acosh(cosh(x)), Q.negative(x)) == acosh(cosh(x))


def test_atanh_tanh_real() -> None:
    assert refine(atanh(tanh(x)), Q.real(x)) == x
    assert_refinement_valid(atanh(tanh(x)), Q.real(x), x)


def test_atanh_tanh_not_real() -> None:
    assert refine(atanh(tanh(x)), Q.imaginary(x)) == atanh(tanh(x))
    assert refine(atanh(tanh(x)), True) == atanh(tanh(x))


def test_acoth_coth_real_nonzero() -> None:
    assumptions = Q.real(x) & Q.nonzero(x)
    assert refine(acoth(coth(x)), assumptions) == x
    assert_refinement_valid(acoth(coth(x)), assumptions, x)


def test_acoth_coth_real_may_be_zero() -> None:
    assert refine(acoth(coth(x)), Q.real(x)) == acoth(coth(x))
    assert refine(acoth(coth(x)), True) == acoth(coth(x))


def test_asech_sech_nonnegative() -> None:
    assert refine(asech(sech(x)), Q.nonnegative(x)) == x
    assert_refinement_valid(asech(sech(x)), Q.nonnegative(x), x)


def test_asech_sech_not_nonnegative() -> None:
    assert refine(asech(sech(x)), Q.real(x)) == asech(sech(x))
    assert refine(asech(sech(x)), Q.negative(x)) == asech(sech(x))


def test_acsch_csch_nonzero() -> None:
    assert refine(acsch(csch(x)), Q.nonzero(x)) == x
    assert_refinement_valid(
        acsch(csch(x)), Q.nonzero(x), x, values={x: NONZERO_REAL_VALUES}
    )


def test_acsch_csch_may_be_zero() -> None:
    assert refine(acsch(csch(x)), Q.real(x)) == acsch(csch(x))
    assert refine(acsch(csch(x)), Q.integer(x)) == acsch(csch(x))


def test_inverse_pairs_do_not_mix() -> None:
    assert refine(asinh(cosh(x)), Q.real(x)) == asinh(cosh(x))
    assert refine(acosh(sinh(x)), Q.nonnegative(x)) == acosh(sinh(x))
    assert refine(atanh(coth(x)), Q.real(x)) == atanh(coth(x))
    assert refine(acoth(tanh(x)), Q.real(x) & Q.nonzero(x)) == acoth(tanh(x))
    assert refine(asech(csch(x)), Q.nonnegative(x)) == asech(csch(x))
    assert refine(acsch(sech(x)), Q.nonzero(x)) == acsch(sech(x))
    assert refine(asinh(sinh(x) + 1), Q.real(x)) == asinh(sinh(x) + 1)


def test_integration_stronger_assumptions() -> None:
    assert refine(asinh(sinh(x)), Q.positive(x)) == x
    assert refine(acoth(coth(x)), Q.nonzero(x)) == x
    assert refine(asech(sech(x)), Q.positive(x)) == x


def test_none_answers_leave_expression_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(asinh(sinh(x)), Q.real(x)) == asinh(sinh(x))
        assert refine(acosh(cosh(x)), Q.nonnegative(x)) == acosh(cosh(x))
        assert refine(atanh(tanh(x)), Q.real(x)) == atanh(tanh(x))
        assert refine(acoth(coth(x)), Q.real(x) & Q.nonzero(x)) == acoth(coth(x))
        assert refine(asech(sech(x)), Q.nonnegative(x)) == asech(sech(x))
        assert refine(acsch(csch(x)), Q.nonzero(x)) == acsch(csch(x))
