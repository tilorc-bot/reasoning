"""Tests for the ``arg`` refine handler (agent report section 3.5).

Keeps the vendored positive/negative behavior and adds the zero edge and the
imaginary half-plane rules from upstream PR #29409:

* ``arg(x) -> nan`` under ``Q.zero(x)``;
* ``arg(x) -> ±pi/2`` under ``Q.imaginary(x)`` only when the sign of ``im(x)``
  is known.

Pinned SymPy has neither addition, so those cases are asserted as documented
divergences; the shared positive/negative cases are compared with
``assert_refines_like_sympy``.
"""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.assumptions.refine import refine as sympy_refine
from sympy.abc import x, z
from sympy.core.numbers import nan, pi
from sympy.functions.elementary.complexes import arg, im

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    scripted_ask,
    stub_ask,
    use_ask,
)


def test_arg_sign_known() -> None:
    assert refine(arg(x), Q.positive(x)) == 0
    assert refine(arg(x), Q.negative(x)) == pi


def test_arg_zero() -> None:
    assert refine(arg(x), Q.zero(x)) is nan


def test_arg_imaginary() -> None:
    assert refine(arg(z), Q.imaginary(z) & Q.positive(im(z))) == pi / 2
    assert refine(arg(z), Q.imaginary(z) & Q.negative(im(z))) == -pi / 2
    assert refine(arg(z), Q.imaginary(z)) == arg(z)


def test_arg_unchanged() -> None:
    assert refine(arg(x)) == arg(x)
    assert refine(arg(x), Q.real(x)) == arg(x)
    assert refine(arg(z), Q.complex(z)) == arg(z)


def test_arg_none_safety() -> None:
    with use_ask(stub_ask({})):
        assert refine(arg(x)) == arg(x)
        assert refine(arg(x), Q.zero(x)) == arg(x)
        assert refine(arg(z), Q.imaginary(z)) == arg(z)

    fake, queries = scripted_ask([None, None, None])
    with use_ask(fake):
        assert refine(arg(x)) == arg(x)
    assert queries[0][0] == Q.positive(x)
    assert queries[1][0] == Q.negative(x)
    assert queries[2][0] == Q.zero(x)


def test_arg_numeric_oracle() -> None:
    assert_refinement_valid(
        arg(x), Q.positive(x), refine(arg(x), Q.positive(x)))
    assert_refinement_valid(
        arg(x), Q.negative(x), refine(arg(x), Q.negative(x)))
    assert_refinement_valid(arg(x), Q.zero(x), refine(arg(x), Q.zero(x)))
    assert_refinement_valid(
        arg(z),
        Q.imaginary(z) & Q.positive(im(z)),
        refine(arg(z), Q.imaginary(z) & Q.positive(im(z))),
    )
    assert_refinement_valid(
        arg(z),
        Q.imaginary(z) & Q.negative(im(z)),
        refine(arg(z), Q.imaginary(z) & Q.negative(im(z))),
    )


def test_arg_reference_ask_shared_cases() -> None:
    assert_refines_like_sympy(arg(x), Q.positive(x))
    assert_refines_like_sympy(arg(x), Q.negative(x))
    assert_refines_like_sympy(arg(x), Q.real(x))


def test_arg_documented_divergences() -> None:
    # Pinned SymPy has no zero or imaginary-argument rules.
    assert sympy_refine(arg(x), Q.zero(x)) == arg(x)
    assert refine(arg(x), Q.zero(x)) is nan
    assert sympy_refine(arg(z), Q.imaginary(z) & Q.positive(im(z))) == arg(z)
    assert refine(arg(z), Q.imaginary(z) & Q.positive(im(z))) == pi / 2
