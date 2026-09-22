"""Tests for the ``conjugate`` refine handler (agent report section 3.5).

Basic rules only: real, imaginary, integer-power, and the product pair
``z*conjugate(z) -> Abs(z)**2``.  Branch-cut-heavy conjugate rules for
``log``/inverse trigonometric functions are deliberately absent (deferred
research item), so nothing here compares against a pinned SymPy handler:
upstream has none, and pinned ``sympy.refine`` leaves every conjugate
expression unchanged.

The product-pair rule acts on a ``Mul``, which the class-keyed dispatcher can
never route to the ``conjugate`` key, so this module also registers the
auxiliary ``Mul`` key (upstream PR #29173 implemented the same rule as a
``refine_Mul``).
"""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import n, x, y, z
from sympy.core.numbers import I
from sympy.functions.elementary.complexes import Abs, conjugate

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    scripted_ask,
    stub_ask,
    use_ask,
)


def test_conjugate_real() -> None:
    assert refine(conjugate(x), Q.real(x)) == x
    assert refine(conjugate(x), Q.positive(x)) == x
    assert refine(conjugate(x), Q.negative(x)) == x
    assert refine(conjugate(x), Q.zero(x)) == x


def test_conjugate_imaginary() -> None:
    assert refine(conjugate(x), Q.imaginary(x)) == -x


def test_conjugate_unchanged() -> None:
    assert refine(conjugate(x)) == conjugate(x)
    assert refine(conjugate(x), Q.complex(x)) == conjugate(x)


def test_conjugate_integer_power() -> None:
    assert refine(conjugate(x**n), Q.imaginary(x) & Q.integer(n)) == (-x)**n
    assert refine(conjugate(x**n), Q.real(x) & Q.integer(n)) == x**n
    assert refine(conjugate(x**2), Q.imaginary(x)) == x**2


def test_conjugate_integer_power_negative() -> None:
    # The base must be known complex for the integer-power rule to fire.
    assert refine(conjugate(x**n), Q.integer(n)) == conjugate(x**n)
    # The exponent must be known integer.
    assert refine(conjugate(x**n), Q.imaginary(x)) == conjugate(x**n)


def test_conjugate_pair_product() -> None:
    assert refine(z * conjugate(z)) == Abs(z)**2
    assert refine(2 * z * conjugate(z)) == 2 * Abs(z)**2
    assert refine(I * z * conjugate(z)) == I * Abs(z)**2
    assert (refine(x * conjugate(x) * y * conjugate(y))
            == Abs(x)**2 * Abs(y)**2)


def test_conjugate_pair_product_negative() -> None:
    assert refine(x * conjugate(y)) == x * conjugate(y)
    assert refine(conjugate(x)) == conjugate(x)
    # A known-real factor is refined to itself first, so the pair vanishes.
    assert refine(z * conjugate(z), Q.real(z)) == z**2


def test_conjugate_none_safety() -> None:
    with use_ask(stub_ask({})):
        assert refine(conjugate(x)) == conjugate(x)
        assert refine(conjugate(x**n)) == conjugate(x**n)
        # The Mul pair rule needs no query at all.
        assert refine(z * conjugate(z)) == Abs(z)**2

    fake, queries = scripted_ask([None, None, None])
    with use_ask(fake):
        assert refine(conjugate(x**n)) == conjugate(x**n)
    assert [query[0] for query in queries] == [
        Q.real(x), Q.real(x**n), Q.imaginary(x**n), Q.integer(n)]


def test_conjugate_numeric_oracle() -> None:
    assert_refinement_valid(
        conjugate(x), Q.real(x), refine(conjugate(x), Q.real(x)))
    assert_refinement_valid(
        conjugate(x), Q.imaginary(x), refine(conjugate(x), Q.imaginary(x)))
    assert_refinement_valid(z * conjugate(z), True, refine(z * conjugate(z)))
    assert_refinement_valid(
        conjugate(x**n),
        Q.imaginary(x) & Q.integer(n),
        refine(conjugate(x**n), Q.imaginary(x) & Q.integer(n)),
    )


def test_conjugate_reference_ask(reference_ask: None) -> None:
    """The quoted PR #29173 basic outputs, independent of the local engine."""
    assert refine(conjugate(x), Q.real(x)) == x
    assert refine(conjugate(x), Q.imaginary(x)) == -x
    assert refine(1 + conjugate(x), Q.real(x)) == 1 + x
    assert refine(conjugate(x * y), Q.real(x) & Q.imaginary(y)) == -x * y
    assert refine(conjugate(x**n), Q.imaginary(x) & Q.integer(n)) == (-x)**n
