"""Tests for the inverse trigonometric refine handlers."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x
from sympy.core import S
from sympy.core.numbers import Rational
from sympy.functions.elementary.trigonometric import (
    acos,
    asin,
    atan,
    cos,
    sin,
    tan,
)

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    stub_ask,
    use_ask,
)


ASIN_RECTANGLE = Q.real(x) & Q.ge(x, -S.Pi / 2) & Q.le(x, S.Pi / 2)
ACOS_RECTANGLE = Q.real(x) & Q.ge(x, 0) & Q.le(x, S.Pi)

REAL_VALUES = [
    S.Zero,
    S.One,
    S.NegativeOne,
    S.Half,
    Rational(-1, 2),
    S(2),
    S(-2),
    S(3),
    Rational(4, 3),
]


def test_asin_sin_principal_branch() -> None:
    assert refine(asin(sin(x)), ASIN_RECTANGLE) == x
    assert_refinement_valid(
        asin(sin(x)), ASIN_RECTANGLE, x, values={x: REAL_VALUES}
    )


def test_acos_cos_principal_branch() -> None:
    assert refine(acos(cos(x)), ACOS_RECTANGLE) == x
    assert_refinement_valid(
        acos(cos(x)), ACOS_RECTANGLE, x, values={x: REAL_VALUES}
    )


def test_atan_tan_principal_branch() -> None:
    assert refine(atan(tan(x)), ASIN_RECTANGLE) == x
    assert_refinement_valid(
        atan(tan(x)), ASIN_RECTANGLE, x, values={x: REAL_VALUES}
    )


def test_asin_sin_outside_branch() -> None:
    assert refine(asin(sin(x)), Q.real(x)) == asin(sin(x))
    mirrored = Q.real(x) & Q.ge(x, S.Pi / 2) & Q.le(x, 3 * S.Pi / 2)
    assert refine(asin(sin(x)), mirrored) == asin(sin(x))


def test_acos_cos_outside_branch() -> None:
    below = Q.real(x) & Q.ge(x, -S.Pi) & Q.le(x, 0)
    assert refine(acos(cos(x)), below) == acos(cos(x))
    assert refine(acos(cos(x)), Q.real(x)) == acos(cos(x))


def test_atan_tan_outside_branch() -> None:
    mirrored = Q.real(x) & Q.ge(x, S.Pi / 2) & Q.le(x, 3 * S.Pi / 2)
    assert refine(atan(tan(x)), mirrored) == atan(tan(x))
    assert refine(atan(tan(x)), Q.real(x)) == atan(tan(x))


def test_partial_range_is_not_enough() -> None:
    assert refine(asin(sin(x)), Q.real(x) & Q.ge(x, -S.Pi / 2)) == asin(sin(x))
    assert refine(asin(sin(x)), Q.real(x) & Q.le(x, S.Pi / 2)) == asin(sin(x))
    assert refine(acos(cos(x)), Q.real(x) & Q.ge(x, 0)) == acos(cos(x))
    assert refine(acos(cos(x)), Q.real(x) & Q.le(x, S.Pi)) == acos(cos(x))


def test_only_matching_inner_function() -> None:
    assert refine(asin(cos(x)), ASIN_RECTANGLE) == asin(cos(x))
    assert refine(acos(sin(x)), ACOS_RECTANGLE) == acos(sin(x))
    assert refine(atan(sin(x)), ASIN_RECTANGLE) == atan(sin(x))
    assert refine(asin(x), ASIN_RECTANGLE) == asin(x)
    assert refine(acos(x), ACOS_RECTANGLE) == acos(x)
    assert refine(atan(x), ASIN_RECTANGLE) == atan(x)


def test_extra_assumptions_still_apply() -> None:
    assert refine(asin(sin(x)), ASIN_RECTANGLE & Q.nonzero(x)) == x
    assert refine(atan(tan(x)), ASIN_RECTANGLE & Q.positive(x)) == x


def test_none_answers_leave_expression_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(asin(sin(x)), ASIN_RECTANGLE) == asin(sin(x))
        assert refine(acos(cos(x)), ACOS_RECTANGLE) == acos(cos(x))
        assert refine(atan(tan(x)), ASIN_RECTANGLE) == atan(tan(x))
