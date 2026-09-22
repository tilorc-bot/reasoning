"""Tests for the ``Max`` refine handler.

Rules from the missing-handler report section 3.9: two-argument order
relations, the ``0`` shortcuts when one argument is ``0``, single-maximum
selection for longer argument lists, and provably infinite arguments.  An
``ask`` answer of ``None`` never refines.
"""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x, y, z
from sympy.core import S
from sympy.core.numbers import oo
from sympy.functions.elementary.miscellaneous import Max

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    recording_ask,
    stub_ask,
    use_ask,
)

REALS = [-2, -1, 0, 1, 2]
POSITIVE = [1, 2]


def test_two_argument_order_rules() -> None:
    assert refine(Max(x, y), Q.ge(x, y)) == x
    assert refine(Max(x, y), Q.le(x, y)) == y
    assert refine(Max(x, y), Q.gt(x, y)) == x
    assert refine(Max(x, y), Q.lt(x, y)) == y


def test_zero_argument_rules() -> None:
    assert refine(Max(x, 0), Q.positive(x)) == x
    assert refine(Max(x, 0), Q.zero(x)) is S.Zero
    assert refine(Max(x, 0), Q.nonnegative(x)) == x
    assert refine(Max(x, 0), Q.negative(x)) is S.Zero
    assert refine(Max(x, 0), Q.nonpositive(x)) is S.Zero


def test_multi_argument_single_maximum() -> None:
    assert refine(Max(x, y, z), Q.ge(x, y) & Q.ge(x, z)) == x
    assert refine(Max(x, y, z), Q.ge(z, x) & Q.ge(z, y)) == z
    assert refine(Max(x, y, z), Q.le(y, x) & Q.le(z, x)) == x
    assert refine(Max(x, y, z), Q.gt(x, y) & Q.gt(x, z)) == x


def test_multi_argument_without_single_maximum_unchanged() -> None:
    # x is only known to beat y; z is still a candidate for the maximum.
    assert refine(Max(x, y, z), Q.ge(x, y)) == Max(x, y, z)
    assert refine(Max(x, y, z), Q.ge(x, y) & Q.ge(z, y)) == Max(x, y, z)


def test_infinite_arguments() -> None:
    assert refine(Max(x, y), Q.positive_infinite(x)) == x
    assert refine(Max(x, y), Q.positive_infinite(y)) == y
    assert refine(Max(x, y), Q.negative_infinite(x)) == y
    assert refine(Max(x, y), Q.negative_infinite(y)) == x
    assert refine(
        Max(x, y), Q.negative_infinite(x) & Q.negative_infinite(y)
    ) is S.NegativeInfinity
    assert refine(Max(x, 0), Q.negative_infinite(x)) is S.Zero
    # literal infinities already evaluate while the arguments are refined
    assert refine(Max(x, oo)) is S.Infinity
    assert refine(Max(x, -oo)) == x


def test_unmet_assumptions_unchanged() -> None:
    assert refine(Max(x, y), True) == Max(x, y)
    assert refine(Max(x, y), Q.real(x) & Q.real(y)) == Max(x, y)
    assert refine(Max(x, y), Q.positive(x) & Q.negative(y)) == Max(x, y)
    assert refine(Max(x, y), Q.eq(x, y)) == Max(x, y)
    assert refine(Max(x, 0), Q.positive(y)) == Max(x, 0)
    assert refine(Max(x, y), Q.infinite(x)) == Max(x, y)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(Max(x, y), Q.ge(x, y)) == Max(x, y)
        assert refine(Max(x, 0), Q.positive(x)) == Max(x, 0)
        assert refine(Max(x, y, z), Q.ge(x, y) & Q.ge(x, z)) == Max(x, y, z)
        assert refine(Max(x, y), Q.negative_infinite(x)) == Max(x, y)


def test_numeric_oracle() -> None:
    assert_refinement_valid(Max(x, y), Q.ge(x, y), x, values={x: REALS, y: REALS})
    assert_refinement_valid(Max(x, y), Q.le(x, y), y, values={x: REALS, y: REALS})
    assert_refinement_valid(
        Max(x, 0), Q.positive(x), x, values={x: POSITIVE}
    )
    assert_refinement_valid(Max(x, 0), Q.zero(x), S.Zero, values={x: [0]})
    assert_refinement_valid(
        Max(x, y, z),
        Q.ge(x, y) & Q.ge(x, z),
        x,
        values={x: REALS, y: REALS, z: REALS},
    )
    assert_refinement_valid(
        Max(x, y), Q.positive_infinite(x), x, values={x: [oo], y: REALS}
    )
    assert_refinement_valid(
        Max(x, y), Q.negative_infinite(x), y, values={x: [-oo], y: REALS}
    )


def test_fidelity_when_sympy_does_not_refine() -> None:
    assert_refines_like_sympy(Max(x, y), Q.real(x) & Q.real(y))


def test_ask_goes_through_upstream() -> None:
    # The first candidate x asks y <= x; the engine answers only the
    # reversed-order form Q.ge(x, y), which the handler accepts.
    fake, log = recording_ask({str(Q.ge(x, y)): True})
    with use_ask(fake):
        assert refine(Max(x, y), Q.ge(x, y)) == x
    assert [entry[0] for entry in log] == [Q.le(y, x), Q.lt(y, x), Q.ge(x, y)]
