"""Tests for the ``Mod`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import p, q, x
from sympy.core import S
from sympy.core.mod import Mod
from sympy.functions.elementary.integers import floor

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    recording_ask,
    stub_ask,
    use_ask,
)

INTEGERS = [-4, -3, -2, -1, 0, 1, 2, 3, 4]
NONZERO_INTEGERS = [-3, -2, -1, 1, 2, 3]


def test_mod_one_under_integer() -> None:
    assert refine(Mod(p, 1), Q.integer(p)) is S.Zero
    assert refine(Mod(p, 1), Q.even(p)) is S.Zero
    assert refine(Mod(p, 1), Q.odd(p)) is S.Zero


def test_exact_quotient_is_zero() -> None:
    assert refine(Mod(5 * x, 5), Q.integer(x)) is S.Zero
    assert refine(Mod(p, p), Q.integer(p)) is S.Zero
    assert refine(Mod(p, -1), Q.integer(p)) is S.Zero


def test_even_odd_mod_two() -> None:
    assert refine(Mod(p, 2), Q.even(p)) is S.Zero
    assert refine(Mod(p, 2), Q.odd(p)) is S.One


def test_integer_pair_uses_floor_definition() -> None:
    expected = p - q * floor(p / q)
    assert refine(Mod(p, q), Q.integer(p) & Q.integer(q)) == expected


def test_sign_variants_share_the_floor_definition() -> None:
    expected = p - q * floor(p / q)
    assert refine(
        Mod(p, q), Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.positive(q)
    ) == expected
    assert refine(
        Mod(p, q), Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.negative(q)
    ) == expected
    assert refine(
        Mod(p, q), Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.negative(q)
    ) == expected
    assert refine(
        Mod(p, q), Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.positive(q)
    ) == expected


def test_unmet_assumptions_unchanged() -> None:
    assert refine(Mod(p, q), Q.real(p) & Q.real(q)) == Mod(p, q)
    assert refine(Mod(p, q), Q.integer(p)) == Mod(p, q)
    assert refine(Mod(p, 3), Q.real(p)) == Mod(p, 3)
    assert refine(Mod(p, 2), Q.positive(p)) == Mod(p, 2)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(Mod(p, 1), Q.integer(p)) == Mod(p, 1)
        assert refine(Mod(p, 2), Q.even(p)) == Mod(p, 2)
        assert refine(Mod(p, q), Q.integer(p) & Q.integer(q)) == Mod(p, q)


def test_numeric_oracle() -> None:
    assert_refinement_valid(
        Mod(p, 1), Q.integer(p), S.Zero, values={p: INTEGERS}
    )
    assert_refinement_valid(
        Mod(p, 2), Q.even(p), S.Zero, values={p: INTEGERS}
    )
    assert_refinement_valid(
        Mod(p, 2), Q.odd(p), S.One, values={p: INTEGERS}
    )
    assert_refinement_valid(
        Mod(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonzero(q),
        p - q * floor(p / q),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )
    assert_refinement_valid(
        Mod(p, q),
        Q.integer(p) & Q.integer(q) & Q.negative(q),
        p - q * floor(p / q),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )
    assert_refinement_valid(
        Mod(5 * x, 5), Q.integer(x), S.Zero, values={x: INTEGERS}
    )


def test_asks_the_quotient_first() -> None:
    fake, log = recording_ask({str(Q.integer(p)): True})
    with use_ask(fake):
        assert refine(Mod(p, 1), Q.integer(p)) is S.Zero
    assert [entry[0] for entry in log] == [Q.integer(p)]
