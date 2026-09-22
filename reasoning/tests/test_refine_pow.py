"""Tests for the ``Pow`` refine handler (agent report section 3.4).

Covers the nested-power casework that replaces the wrong unconditional
``(z1**z2)**z3 -> Abs(z1)**(z2*z3)`` rewrite (issue #29684, PR #29800), the
``Abs(z)**even`` rule under ``Q.imaginary(z)`` (issue #30473, PRs
#30474/#30476) and the ``Pow(E, x)`` delegation to the ``exp`` handler
(PR #30248).  The vendored ``(-1)**Add`` machinery and the remaining Abs/mul
behavior are delegated unchanged and compared with ``assert_refines_like_sympy``.

Documented divergences from pinned SymPy (asserted, not compared):

* ``(x**3)**Rational(1, 2)`` under ``Q.real(x)``: pinned SymPy still returns
  the wrong ``Abs(x)**(3/2)``, we leave it unchanged;
* ``Abs(z)**2`` under ``Q.imaginary(z)``: pinned SymPy leaves it unchanged,
  we return ``-z**2``.
"""
from __future__ import annotations

import pytest
from sympy.assumptions import Q
from sympy.assumptions.refine import refine as sympy_refine
from sympy.abc import n, x, y, z
from sympy.core import Pow, Rational, S
from sympy.core.numbers import I, pi
from sympy.functions.elementary.complexes import Abs
from sympy.functions.elementary.exponential import exp
from sympy.functions.elementary.miscellaneous import sqrt

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    scripted_ask,
    stub_ask,
    use_ask,
)


def test_nested_power_integer_outer() -> None:
    assert refine((x**2)**3) == x**6
    assert refine((x**y)**z, Q.integer(z)) == x**(y * z)


def test_nested_power_positive_base() -> None:
    assert refine((x**3)**Rational(1, 3), Q.positive(x)) == x
    assert refine((x**y)**z, Q.positive(x) & Q.real(y)) == x**(y * z)
    assert refine(sqrt(1 / x), Q.positive(x)) == 1 / sqrt(x)


def test_nested_power_real_base_even_inner() -> None:
    assert refine(sqrt(x**2), Q.real(x)) == Abs(x)
    assert refine((x**2)**Rational(1, 2), Q.real(x)) == Abs(x)
    assert refine(sqrt(x**4), Q.real(x)) == x**2
    assert refine((x**y)**z, Q.real(x) & Q.even(y)) == Abs(x)**(y * z)


def test_nested_power_bug_regression_29684() -> None:
    refined_sqrt = refine((x**3)**Rational(1, 2), Q.real(x))
    assert refined_sqrt == sqrt(x**3)
    assert refined_sqrt != Abs(x)**Rational(3, 2)

    refined_cbrt = refine((x**3)**Rational(1, 3), Q.real(x))
    assert refined_cbrt == (x**3)**Rational(1, 3)
    assert refined_cbrt != Abs(x)
    assert refine((x**3)**Rational(1, 3)) != x
    assert refine(sqrt(1 / x), Q.real(x)) != 1 / sqrt(x)


def test_nested_power_numeric_oracle() -> None:
    # The old wrong rewrite is rejected by the oracle at x = -2:
    # sqrt(-8) = 2*sqrt(2)*I but Abs(-2)**(3/2) = 2*sqrt(2).
    with pytest.raises(AssertionError):
        assert_refinement_valid(
            (x**3)**Rational(1, 2), Q.real(x), Abs(x)**Rational(3, 2))

    refined = refine((x**3)**Rational(1, 2), Q.real(x))
    assert_refinement_valid((x**3)**Rational(1, 2), Q.real(x), refined)
    refined = refine((x**3)**Rational(1, 3), Q.real(x))
    assert_refinement_valid((x**3)**Rational(1, 3), Q.real(x), refined)
    refined = refine((x**3)**Rational(1, 3), Q.positive(x))
    assert refined == x
    assert_refinement_valid((x**3)**Rational(1, 3), Q.positive(x), refined)
    refined = refine(sqrt(x**2), Q.real(x))
    assert refined == Abs(x)
    assert_refinement_valid(sqrt(x**2), Q.real(x), refined)
    refined = refine(sqrt(x**4), Q.real(x))
    assert refined == x**2
    assert_refinement_valid(sqrt(x**4), Q.real(x), refined)


def test_abs_power_imaginary() -> None:
    assert refine(Abs(z)**2, Q.imaginary(z)) == -z**2
    assert refine(Abs(z)**4, Q.imaginary(z)) == z**4
    assert (refine(Abs(z)**(2 * n), Q.imaginary(z) & Q.integer(n))
            == (-1)**n * z**(2 * n))
    assert refine(Abs(z)**3, Q.imaginary(z)) == Abs(z)**3
    assert refine(Abs(z)**2) == Abs(z)**2


def test_abs_power_imaginary_numeric_oracle() -> None:
    assert_refinement_valid(
        Abs(z)**2, Q.imaginary(z), refine(Abs(z)**2, Q.imaginary(z)))
    assert_refinement_valid(
        Abs(z)**4, Q.imaginary(z), refine(Abs(z)**4, Q.imaginary(z)))
    assert_refinement_valid(
        Abs(z)**(2 * n),
        Q.imaginary(z) & Q.integer(n),
        refine(Abs(z)**(2 * n), Q.imaginary(z) & Q.integer(n)),
    )


def test_pow_exp_delegation() -> None:
    assert refine(exp(pi * I * 2 * x), Q.integer(x)) == 1
    assert refine(Pow(S.Exp1, pi * I * 2 * x, evaluate=False), Q.integer(x)) == 1
    assert (refine(Pow(S.Exp1, pi * I * x, evaluate=False), Q.integer(x))
            == (-1)**x)
    # The unevaluated form and the exp form stay in sync through the rebuild.
    assert (refine(Pow(S.Exp1, x, evaluate=False), Q.even(x))
            == refine(exp(x), Q.even(x)))


def test_pow_vendored_behavior_retained() -> None:
    assert refine((-1)**x, Q.even(x)) == 1
    assert refine((-1)**x, Q.odd(x)) == -1
    assert refine((-2)**x, Q.even(x)) == 2**x
    assert refine((-1)**(x + y), Q.even(x)) == (-1)**y
    assert refine((-1)**(x + y + z), Q.odd(x) & Q.odd(z)) == (-1)**y
    assert refine((-1)**(x + y + 2), Q.odd(x)) == (-1)**(y + 1)
    assert refine((-1)**((-1)**x / 2 - S.Half), Q.integer(x)) == (-1)**x
    assert refine(Abs(x)**2, Q.real(x)) == x**2
    assert refine(Abs(x)**3, Q.real(x)) == Abs(x)**3


def test_pow_reference_ask_shared_cases() -> None:
    assert_refines_like_sympy((-1)**x, Q.even(x))
    assert_refines_like_sympy((-2)**x, Q.even(x))
    assert_refines_like_sympy((-1)**(x + y), Q.even(x))
    assert_refines_like_sympy(Abs(x)**2, Q.real(x))
    assert_refines_like_sympy(Abs(x)**3, Q.real(x))
    assert_refines_like_sympy((x**2)**3)
    assert_refines_like_sympy((x**3)**Rational(1, 3), Q.positive(x))
    assert_refines_like_sympy((x**3)**Rational(1, 2), Q.positive(x))
    assert_refines_like_sympy(sqrt(x**4), Q.real(x))


def test_pow_documented_divergences() -> None:
    # issue #29684: pinned SymPy still applies the unconditional abs rewrite.
    assert (sympy_refine((x**3)**Rational(1, 2), Q.real(x))
            == Abs(x)**Rational(3, 2))
    assert refine((x**3)**Rational(1, 2), Q.real(x)) == sqrt(x**3)

    # issue #30473: pinned SymPy has no imaginary-Abs rule.
    assert sympy_refine(Abs(z)**2, Q.imaginary(z)) == Abs(z)**2
    assert refine(Abs(z)**2, Q.imaginary(z)) == -z**2


def test_pow_none_safety() -> None:
    with use_ask(stub_ask({})):
        assert refine((x**3)**Rational(1, 2), Q.real(x)) == sqrt(x**3)
        assert refine((x**2)**Rational(1, 2), Q.real(x)) == sqrt(x**2)
        assert refine(Abs(z)**2, Q.imaginary(z)) == Abs(z)**2
        assert refine(Abs(x)**2) == Abs(x)**2

    fake, queries = scripted_ask([None, None])
    with use_ask(fake):
        assert refine((x**y)**z, Q.integer(z)) == (x**y)**z
    assert queries[0][0] == Q.real(x)
