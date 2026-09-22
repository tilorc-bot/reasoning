"""Tests for the ``sign`` refine handler (agent report section 3.5).

The vendored ``refine_sign`` asks ``Q.real(arg)``/``Q.imaginary(arg)`` without
passing ``assumptions`` (upstream PR #29605); this handler passes them through,
which makes the plain-symbol real cases work.  Old-assumption symbols
(``Symbol('y', imaginary=True)``) are not visible to the independent engine,
so the imaginary old-assumption case is a strict xfail naming the missing
query.  Pinned SymPy still shows the dropped-assumptions bug, so the
plain-symbol real case is asserted as a documented divergence instead of being
compared.
"""
from __future__ import annotations

import pytest
from sympy.assumptions import Q
from sympy.assumptions.refine import refine as sympy_refine
from sympy.abc import x, z
from sympy.core.numbers import I
from sympy.core.symbol import Symbol
from sympy.functions.elementary.complexes import Abs, im, sign

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    scripted_ask,
    stub_ask,
    use_ask,
)


def test_sign_real_cases() -> None:
    assert refine(sign(x), Q.positive(x)) == 1
    assert refine(sign(x), Q.negative(x)) == -1
    assert refine(sign(x), Q.zero(x)) == 0
    assert refine(sign(x), Q.real(x)) == sign(x)


def test_sign_imaginary_cases() -> None:
    assert refine(sign(z), Q.imaginary(z) & Q.positive(im(z))) == I
    assert refine(sign(z), Q.imaginary(z) & Q.negative(im(z))) == -I
    # Without the sign of the imaginary part both branches are possible.
    assert refine(sign(z), Q.imaginary(z)) == sign(z)


def test_sign_unchanged() -> None:
    assert refine(sign(x)) == sign(x)
    assert refine(sign(x), Q.complex(x)) == sign(x)
    assert refine(sign(Abs(x)), Q.nonzero(x)) == 1


def test_sign_none_safety() -> None:
    with use_ask(stub_ask({})):
        assert refine(sign(x), Q.positive(x)) == sign(x)
        assert refine(sign(z), Q.imaginary(z) & Q.positive(im(z))) == sign(z)

    fake, queries = scripted_ask([None, None, None])
    with use_ask(fake):
        assert refine(sign(x), Q.positive(x)) == sign(x)
    assert queries[0][0] == Q.zero(x)


def test_sign_numeric_oracle() -> None:
    assert_refinement_valid(
        sign(x), Q.positive(x), refine(sign(x), Q.positive(x)))
    assert_refinement_valid(
        sign(x), Q.negative(x), refine(sign(x), Q.negative(x)))
    assert_refinement_valid(sign(x), Q.zero(x), refine(sign(x), Q.zero(x)))
    assert_refinement_valid(
        sign(z),
        Q.imaginary(z) & Q.positive(im(z)),
        refine(sign(z), Q.imaginary(z) & Q.positive(im(z))),
    )
    assert_refinement_valid(
        sign(z),
        Q.imaginary(z) & Q.negative(im(z)),
        refine(sign(z), Q.imaginary(z) & Q.negative(im(z))),
    )


def test_sign_reference_ask_shared_cases() -> None:
    assert_refines_like_sympy(sign(x), Q.zero(x))
    assert_refines_like_sympy(sign(x), Q.real(x))
    assert_refines_like_sympy(sign(Abs(x)), Q.nonzero(x))
    assert_refines_like_sympy(sign(x), Q.imaginary(x))


def test_sign_documented_divergence() -> None:
    # Pinned SymPy drops the assumptions on its Q.real/Q.imaginary checks.
    assert sympy_refine(sign(x), Q.positive(x)) == sign(x)
    assert refine(sign(x), Q.positive(x)) == 1


@pytest.mark.xfail(
    strict=True,
    reason="old-assumption bridge missing: ask(Q.imaginary(y)) returns None "
           "for Symbol('y', imaginary=True)",
)
def test_sign_old_assumption_imaginary_symbol() -> None:
    y = Symbol('y', imaginary=True)
    assert refine(sign(y), Q.positive(im(y))) == I
