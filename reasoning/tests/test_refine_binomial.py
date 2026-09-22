"""Tests for the ``binomial`` refine handler.

The support rule quoted in the report omits ``Q.integer(k)``; without it the
rule is false (``binomial(2, 3/2) = 16/(3*pi)``), so the handler requires it.
"""
from __future__ import annotations

import pytest
from sympy.assumptions import Q
from sympy.abc import k, n
from sympy.core import S
from sympy.core.numbers import Rational
from sympy.functions.combinatorial.factorials import binomial

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    recording_ask,
    stub_ask,
    use_ask,
)

INTEGERS = [-4, -3, -2, -1, 0, 1, 2, 3, 4]


def test_zero_k_is_one() -> None:
    assert refine(binomial(n, k), Q.zero(k)) is S.One


def test_one_k_is_n() -> None:
    assert refine(binomial(n, k), Q.eq(k, 1)) == n


def test_negative_integer_k_is_zero() -> None:
    assert refine(binomial(n, k), Q.integer(k) & Q.negative(k)) is S.Zero


def test_support_case_is_zero() -> None:
    assumptions = (
        Q.integer(n) & Q.nonnegative(n) & Q.integer(k) & Q.negative(n - k)
    )
    assert refine(binomial(n, k), assumptions) is S.Zero
    assert refine(binomial(n, k), assumptions & Q.positive(k)) is S.Zero


def test_support_case_needs_integer_k() -> None:
    # Without Q.integer(k) no refinement is justified or returned.
    assumptions = Q.integer(n) & Q.nonnegative(n) & Q.negative(n - k)
    assert refine(binomial(n, k), assumptions) == binomial(n, k)


def test_unmet_assumptions_unchanged() -> None:
    assert refine(binomial(n, k), Q.real(n) & Q.real(k)) == binomial(n, k)
    assert refine(binomial(n, k), Q.integer(k)) == binomial(n, k)
    assert refine(binomial(n, k), Q.integer(n) & Q.nonnegative(n)) == binomial(n, k)
    assert refine(binomial(n, k), Q.positive(k)) == binomial(n, k)


def test_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(binomial(n, k), Q.zero(k)) == binomial(n, k)
        assert refine(binomial(n, k), Q.eq(k, 1)) == binomial(n, k)
        assert refine(binomial(n, k), Q.integer(k) & Q.negative(k)) == binomial(n, k)
        assert refine(
            binomial(n, k),
            Q.integer(n) & Q.nonnegative(n) & Q.integer(k) & Q.negative(n - k),
        ) == binomial(n, k)


def test_numeric_oracle() -> None:
    assert_refinement_valid(binomial(n, k), Q.zero(k), S.One)
    assert_refinement_valid(binomial(n, k), Q.eq(k, 1), n)
    assert_refinement_valid(
        binomial(n, k),
        Q.integer(k) & Q.negative(k),
        S.Zero,
        values={k: [-4, -3, -2, -1]},
    )
    assert_refinement_valid(
        binomial(n, k),
        Q.integer(n) & Q.nonnegative(n) & Q.integer(k) & Q.negative(n - k),
        S.Zero,
        values={n: INTEGERS, k: INTEGERS},
    )


def test_support_case_oracle_catches_missing_integer_k() -> None:
    # Documents why the handler is stricter than the quoted report rule.
    with pytest.raises(AssertionError, match="invalid"):
        assert_refinement_valid(
            binomial(n, k),
            Q.integer(n) & Q.nonnegative(n) & Q.negative(n - k),
            S.Zero,
            values={n: [0, 2], k: [Rational(4, 3), 3]},
        )


def test_ask_goes_through_upstream() -> None:
    fake, log = recording_ask({str(Q.zero(k)): True})
    with use_ask(fake):
        assert refine(binomial(n, k), Q.zero(k)) is S.One
    assert [entry[0] for entry in log] == [Q.zero(k)]
