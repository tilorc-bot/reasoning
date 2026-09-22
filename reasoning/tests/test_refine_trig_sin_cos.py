"""Tests for the guarded ``sin``/``cos`` refine handler.

The handler is a copy of the vendored
:func:`reasoning.refine._upstream.refine_sin_cos` with the PR #29450 guard
for the ``(-1)**(k/2)`` factor that can evaluate to an ``Integer``.
"""
from __future__ import annotations

import pytest
from sympy.assumptions import Q
from sympy.abc import x, y
from sympy.calculus.accumulationbounds import AccumBounds
from sympy.core import S
from sympy.core.symbol import Symbol
from sympy.functions.elementary.exponential import exp
from sympy.functions.elementary.trigonometric import cos, sin, tan

from reasoning.refine import refine
from reasoning.refine.handlers.trig_sin_cos import refine_sin_cos
from reasoning.tests.refine_harness import (
    assert_refines_like_sympy,
    assert_refinement_valid,
    stub_ask,
    use_ask,
)


def test_zero_argument() -> None:
    assert refine(sin(x), Q.zero(x)) == 0
    assert refine(cos(x), Q.zero(x)) == 1
    assert_refinement_valid(sin(x), Q.zero(x), 0)
    assert_refinement_valid(cos(x), Q.zero(x), 1)


def test_integer_multiple_of_pi() -> None:
    n = Symbol("n")
    assert refine(sin(n * S.Pi), Q.integer(n)) == 0
    assert refine(cos(n * S.Pi), Q.even(n)) == 1
    assert refine(cos(n * S.Pi), Q.odd(n)) == -1
    assert refine(cos(n * S.Pi), Q.integer(n)) == (-1) ** n


def test_parity_known_half_pi_multiple() -> None:
    n = Symbol("n")
    assert refine(sin(n * S.Pi / 2), Q.odd(n) & Q.even((n - 1) / 2)) == 1
    assert refine(sin(n * S.Pi / 2), Q.odd(n) & Q.odd((n - 1) / 2)) == -1
    assert refine(sin(n * S.Pi / 2), Q.even(n)) == 0
    assert refine(cos(n * S.Pi / 2), Q.even(n)) == (-1) ** (n / 2)
    assert refine(cos(n * S.Pi / 2), Q.odd(n)) == 0


def test_shifts() -> None:
    n = Symbol("n")
    assert refine(sin(x + n * S.Pi), Q.integer(n)) == (-1) ** n * sin(x)
    assert refine(cos(x + n * S.Pi), Q.odd(n)) == -cos(x)
    assert refine(sin(x + n * S.Pi / 2), Q.odd(n)) == \
        (-1) ** ((n + 3) / 2) * cos(x)
    assert refine(cos(x + n * S.Pi / 2), Q.odd(n)) == \
        (-1) ** ((n + 1) / 2) * sin(x)
    assert refine(cos(x + y + 2 * n * S.Pi), Q.integer(n)) == cos(x + y)
    assert_refinement_valid(
        sin(x + n * S.Pi), Q.integer(n), (-1) ** n * sin(x)
    )


def test_infinite_argument() -> None:
    assert refine(sin(x), Q.infinite(x) & Q.extended_real(x)) == \
        AccumBounds(-1, 1)
    assert refine(cos(x), Q.infinite(x) & Q.extended_real(x)) == \
        AccumBounds(-1, 1)


def test_no_refinement_when_no_rule_applies() -> None:
    n = Symbol("n")
    assert refine(sin(x), Q.real(x)) == sin(x)
    assert refine(cos(x), Q.integer(x)) == cos(x)
    assert refine(cos(x + n * S.Pi / 2), Q.integer(n)) == \
        cos(x + n * S.Pi / 2)
    assert refine(sin(x), Q.infinite(x)) == sin(x)


def test_none_safe() -> None:
    n = Symbol("n")
    with use_ask(stub_ask({})):
        assert refine(sin(x), Q.zero(x)) == sin(x)
        assert refine(cos(x), Q.zero(x)) == cos(x)
        assert refine(sin(x + n * S.Pi), Q.integer(n)) == \
            sin(x + n * S.Pi)
        assert refine(cos(x + n * S.Pi / 2), Q.odd(n)) == \
            cos(x + n * S.Pi / 2)


def test_matches_sympy_for_handled_cases() -> None:
    n = Symbol("n")
    assert_refines_like_sympy(cos(n * S.Pi), Q.even(n))
    assert_refines_like_sympy(sin(n * S.Pi), Q.integer(n))
    assert_refines_like_sympy(sin(x + n * S.Pi / 2), Q.odd(n))
    assert_refines_like_sympy(cos(x + y + 2 * n * S.Pi), Q.integer(n))
    assert_refines_like_sympy(
        sin(n * S.Pi / 2), Q.odd(n) & Q.even((n - 1) / 2)
    )


def test_type_error_preserved() -> None:
    with pytest.raises(TypeError):
        refine_sin_cos(tan(x), Q.real(x))
    with pytest.raises(TypeError):
        refine_sin_cos(exp(x), Q.real(x))
    with pytest.raises(TypeError):
        refine_sin_cos(x, Q.real(x))


def test_integer_power_factor_regression() -> None:
    # `sin(pi + x)` has a literal `k`, so `(-1)**((k + 1)/2)` is `-1`: calling
    # `refine_Pow` on it used to raise `AttributeError`.
    assert refine_sin_cos(sin(S.Pi + x, evaluate=False), True) == -sin(x)
    assert refine_sin_cos(cos(S.Pi + x, evaluate=False), True) == -cos(x)
    assert refine(sin(S.Pi + x, evaluate=False), True) == -sin(x)


def test_upstream_crash_regression() -> None:
    # Regression report from PR #29450: `(-1)**(2*m)` evaluates to `1` for the
    # integer symbol `m`, so `refine_Pow` must not be called on it.
    m = Symbol("m", integer=True)
    n = Symbol("n", integer=True)
    assert refine(sin(x + 2 * S.Pi * m + S.Pi * n / 2), Q.integer(m)) == \
        sin(x + S.Pi * n / 2)
    assert refine(cos(x + 2 * S.Pi * m + S.Pi * n / 2), Q.integer(m)) == \
        cos(x + S.Pi * n / 2)
