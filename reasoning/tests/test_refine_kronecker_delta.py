"""Tests for the ``KroneckerDelta`` refine handler.

Rules from the missing-handler report section 3.12: ``KroneckerDelta(i, j)``
under ``Q.eq(i, j)`` is ``1`` and under ``Q.ne(i, j)`` is ``0``.  Equality is
never guessed: an unknown or merely related assumption leaves the expression
unchanged.  The engine derives no ``Q.ne`` from a given ``Q.eq``, so the
``Q.ne`` direction is only reached when that assumption is stated directly
(it does answer there), and an ``ask`` answer of ``None`` never refines.
"""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import i, j, k
from sympy.core import S
from sympy.functions.special.tensor_functions import KroneckerDelta

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    recording_ask,
    stub_ask,
    use_ask,
)

INDICES = [-1, 0, 1]


def test_equal_indices_are_one() -> None:
    assert refine(KroneckerDelta(i, j), Q.eq(i, j)) is S.One
    assert refine(KroneckerDelta(i, j), Q.eq(i, j) & Q.integer(i)) is S.One


def test_unequal_indices_are_zero() -> None:
    assert refine(KroneckerDelta(i, j), Q.ne(i, j)) is S.Zero


def test_ne_direction_uses_direct_assumption() -> None:
    # Under a direct Q.ne the Q.eq query answers None, then Q.ne answers True.
    fake, log = recording_ask({str(Q.ne(i, j)): True})
    with use_ask(fake):
        assert refine(KroneckerDelta(i, j), Q.ne(i, j)) is S.Zero
    assert [entry[0] for entry in log] == [Q.eq(i, j), Q.ne(i, j)]


def test_unproven_equality_is_not_guessed() -> None:
    assert refine(KroneckerDelta(i, j), Q.eq(i, k)) == KroneckerDelta(i, j)
    assert refine(KroneckerDelta(i, j), Q.ne(i, k)) == KroneckerDelta(i, j)
    assert refine(KroneckerDelta(i, j), Q.real(i) & Q.real(j)) == KroneckerDelta(i, j)
    assert refine(KroneckerDelta(i, j), Q.integer(i) & Q.integer(j)) == KroneckerDelta(
        i, j
    )
    assert refine(KroneckerDelta(i, j), True) == KroneckerDelta(i, j)


def test_identical_indices_evaluate_at_construction() -> None:
    assert KroneckerDelta(i, i) is S.One
    assert refine(KroneckerDelta(i, i)) is S.One


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(KroneckerDelta(i, j), Q.eq(i, j)) == KroneckerDelta(i, j)
        assert refine(KroneckerDelta(i, j), Q.ne(i, j)) == KroneckerDelta(i, j)


def test_numeric_oracle() -> None:
    assert_refinement_valid(
        KroneckerDelta(i, j), Q.eq(i, j), S.One, values={i: INDICES, j: INDICES}
    )
    assert_refinement_valid(
        KroneckerDelta(i, j), Q.ne(i, j), S.Zero, values={i: INDICES, j: INDICES}
    )


def test_fidelity_when_sympy_does_not_refine() -> None:
    assert_refines_like_sympy(KroneckerDelta(i, j), Q.integer(i) & Q.integer(j))


def test_ask_goes_through_upstream() -> None:
    fake, log = recording_ask({str(Q.eq(i, j)): True})
    with use_ask(fake):
        assert refine(KroneckerDelta(i, j), Q.eq(i, j)) is S.One
    assert [entry[0] for entry in log] == [Q.eq(i, j)]
