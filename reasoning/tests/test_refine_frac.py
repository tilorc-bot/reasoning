"""Tests for the ``frac`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import n, x, y
from sympy.core import S
from sympy.functions.elementary.integers import frac

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    recording_ask,
    stub_ask,
    use_ask,
)


def test_integer_argument_is_zero() -> None:
    assert refine(frac(x), Q.integer(x)) is S.Zero
    assert refine(frac(x), Q.zero(x)) is S.Zero
    assert refine(frac(x), Q.even(x)) is S.Zero
    assert refine(frac(x), Q.odd(x)) is S.Zero


def test_integer_addend_is_dropped() -> None:
    assert refine(frac(x + n), Q.integer(n)) == frac(x)
    assert refine(frac(x + y + n), Q.integer(n)) == frac(x + y)
    assert refine(frac(x + y + n), Q.integer(n) & Q.integer(y)) == frac(x)
    assert refine(frac(x + n), Q.integer(n) & Q.integer(x)) is S.Zero
    assert refine(frac(x + S.Half), Q.integer(x)) == S.Half


def test_unmet_assumptions_unchanged() -> None:
    assert refine(frac(x), Q.real(x)) == frac(x)
    assert refine(frac(x), Q.positive(x)) == frac(x)
    assert refine(frac(x + y), Q.real(x) & Q.real(y)) == frac(x + y)
    assert refine(frac(x + n), Q.real(n)) == frac(x + n)
    assert refine(frac(x + n), Q.nonnegative(n)) == frac(x + n)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(frac(x), Q.integer(x)) == frac(x)
        assert refine(frac(x + y), Q.integer(x)) == frac(x + y)
        assert refine(frac(x + y + n), Q.integer(n)) == frac(x + y + n)


def test_numeric_oracle() -> None:
    assert_refinement_valid(frac(x), Q.integer(x), S.Zero)
    assert_refinement_valid(frac(x), Q.zero(x), S.Zero)
    assert_refinement_valid(frac(x + n), Q.integer(n), frac(x))
    assert_refinement_valid(
        frac(x + y + n), Q.integer(n) & Q.integer(y), frac(x)
    )
    assert_refinement_valid(frac(x + S.Half), Q.integer(x), S.Half)


def test_ask_goes_through_upstream() -> None:
    fake, log = recording_ask({str(Q.integer(x)): True})
    with use_ask(fake):
        assert refine(frac(x), Q.integer(x)) is S.Zero
    assert [entry[0] for entry in log] == [Q.integer(x)]
