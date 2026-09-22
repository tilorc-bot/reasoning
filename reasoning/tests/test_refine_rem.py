"""Tests for the ``Rem`` refine handler.

``Rem(p, q) = p - int(p/q)*q`` (truncated division, sign of ``p``), so the
floor identity only holds when ``p/q >= 0``; the handler restricts itself to
the four sign combinations where truncation is ``floor`` or ``ceiling``.
"""
from __future__ import annotations

import pytest
from sympy.assumptions import Q
from sympy.abc import p, q, x
from sympy.core import S
from sympy.functions.elementary.integers import ceiling, floor
from sympy.functions.elementary.miscellaneous import Rem

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    recording_ask,
    stub_ask,
    use_ask,
)

INTEGERS = [-4, -3, -2, -1, 0, 1, 2, 3, 4]
NONZERO_INTEGERS = [-3, -2, -1, 1, 2, 3]


def test_zero_dividend_is_zero() -> None:
    assert refine(Rem(p, q), Q.zero(p)) is S.Zero
    assert refine(Rem(p, q), Q.zero(p) & Q.nonzero(q)) is S.Zero


def test_exact_quotient_is_zero() -> None:
    assert refine(Rem(5 * x, 5), Q.integer(x)) is S.Zero
    assert refine(Rem(p, p), Q.integer(p)) is S.Zero


def test_same_sign_uses_floor() -> None:
    expected = p - q * floor(p / q)
    assert refine(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.positive(q),
    ) == expected
    assert refine(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.negative(q),
    ) == expected
    assert refine(Rem(p, 3), Q.integer(p) & Q.nonnegative(p)) == p - 3 * floor(p / 3)
    assert refine(Rem(p, -3), Q.integer(p) & Q.nonpositive(p)) == p + 3 * floor(-p / 3)


def test_opposite_sign_uses_ceiling() -> None:
    expected = p - q * ceiling(p / q)
    assert refine(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.negative(q),
    ) == expected
    assert refine(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.positive(q),
    ) == expected
    assert refine(Rem(p, 3), Q.integer(p) & Q.nonpositive(p)) == p - 3 * ceiling(p / 3)
    assert refine(Rem(p, -3), Q.integer(p) & Q.nonnegative(p)) == p + 3 * ceiling(-p / 3)


def test_integer_pair_without_signs_unchanged() -> None:
    # Neither floor nor ceiling is implied, so no refinement is returned.
    assert refine(Rem(p, q), Q.integer(p) & Q.integer(q)) == Rem(p, q)


def test_unmet_assumptions_unchanged() -> None:
    assert refine(Rem(p, q), Q.real(p) & Q.real(q)) == Rem(p, q)
    assert refine(
        Rem(p, q), Q.integer(p) & Q.nonnegative(p)
    ) == Rem(p, q)
    assert refine(
        Rem(p, q), Q.integer(p) & Q.integer(q) & Q.nonnegative(p)
    ) == Rem(p, q)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(Rem(p, q), Q.zero(p)) == Rem(p, q)
        assert refine(
            Rem(p, q),
            Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.positive(q),
        ) == Rem(p, q)


def test_numeric_oracle() -> None:
    assert_refinement_valid(
        Rem(p, q), Q.zero(p) & Q.nonzero(q), S.Zero,
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )
    assert_refinement_valid(
        Rem(5 * x, 5), Q.integer(x), S.Zero, values={x: INTEGERS}
    )
    assert_refinement_valid(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.positive(q),
        p - q * floor(p / q),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )
    assert_refinement_valid(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.negative(q),
        p - q * floor(p / q),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )
    assert_refinement_valid(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.negative(q),
        p - q * ceiling(p / q),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )
    assert_refinement_valid(
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.positive(q),
        p - q * ceiling(p / q),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )


def test_floor_identity_is_not_sound_without_signs() -> None:
    # Guards the deviation from the report: Rem(-2, 3) = -2 but
    # -2 - 3*floor(-2/3) = 1, so integer p and q alone cannot justify floor.
    with pytest.raises(AssertionError, match="invalid"):
        assert_refinement_valid(
            Rem(p, q),
            Q.integer(p) & Q.integer(q),
            p - q * floor(p / q),
            values={p: [-2, 2], q: [-3, 3]},
        )


def test_ask_goes_through_upstream() -> None:
    fake, log = recording_ask({str(Q.zero(p)): True})
    with use_ask(fake):
        assert refine(Rem(p, q), Q.zero(p)) is S.Zero
    assert [entry[0] for entry in log] == [Q.zero(p)]
