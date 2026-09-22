"""Tests for the ``DiracDelta`` refine handler.

Rule from the missing-handler report section 3.12: ``DiracDelta(x)`` under
``Q.nonzero(x)`` is ``0``.  Only the first argument is queried, so the
derivative order in ``DiracDelta(x, k)`` changes nothing, and an ``ask``
answer of ``None`` never refines.
"""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x
from sympy.core import S
from sympy.functions.special.delta_functions import DiracDelta

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    recording_ask,
    stub_ask,
    use_ask,
)

NONZERO = [-2, -1, 1, 2]


def test_nonzero_argument_is_zero() -> None:
    assert refine(DiracDelta(x), Q.nonzero(x)) is S.Zero
    assert refine(DiracDelta(x), Q.positive(x)) is S.Zero
    assert refine(DiracDelta(x), Q.negative(x)) is S.Zero


def test_second_argument_does_not_trigger() -> None:
    # DiracDelta(x, k) only accepts a literal non-negative integer k; the
    # handler still decides on the first argument alone.
    assert refine(DiracDelta(x, 2), Q.nonzero(x)) is S.Zero
    assert refine(DiracDelta(x, 2), Q.nonnegative(x)) == DiracDelta(x, 2)


def test_zero_and_unknown_unchanged() -> None:
    assert refine(DiracDelta(x), Q.zero(x)) == DiracDelta(x)
    assert refine(DiracDelta(x), Q.real(x)) == DiracDelta(x)
    assert refine(DiracDelta(x, 2), Q.zero(x)) == DiracDelta(x, 2)
    assert refine(DiracDelta(x, 2), Q.real(x)) == DiracDelta(x, 2)
    assert refine(DiracDelta(x), True) == DiracDelta(x)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(DiracDelta(x), Q.nonzero(x)) == DiracDelta(x)
        assert refine(DiracDelta(x, 2), Q.nonzero(x)) == DiracDelta(x, 2)


def test_numeric_oracle() -> None:
    assert_refinement_valid(DiracDelta(x), Q.nonzero(x), S.Zero, values={x: NONZERO})
    assert_refinement_valid(
        DiracDelta(x, 2), Q.nonzero(x), S.Zero, values={x: NONZERO}
    )


def test_fidelity_when_sympy_does_not_refine() -> None:
    assert_refines_like_sympy(DiracDelta(x), Q.real(x))


def test_ask_goes_through_upstream() -> None:
    fake, log = recording_ask({str(Q.nonzero(x)): True})
    with use_ask(fake):
        assert refine(DiracDelta(x), Q.nonzero(x)) is S.Zero
    assert [entry[0] for entry in log] == [Q.nonzero(x)]
