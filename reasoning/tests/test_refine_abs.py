"""Tests for the ``Abs`` refine handler (agent report section 3.5).

The only change over the vendored handler is the zero case: ``Abs(x) -> 0``
under ``Q.zero(x)``, where pinned SymPy returns ``x`` (PRs #29183/#29796).
Everything else (positive/negative arguments, the ``Mul`` factor split and
the Add-sign path enabled by the structural facts) is delegated and compared
with ``assert_refines_like_sympy``.
"""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.assumptions.refine import refine as sympy_refine
from sympy.abc import x, y, z
from sympy.core import S
from sympy.functions.elementary.complexes import Abs

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    scripted_ask,
    stub_ask,
    use_ask,
)


def test_abs_zero() -> None:
    assert refine(Abs(x), Q.zero(x)) == 0
    assert refine(Abs(x), Q.zero(x)) is S.Zero


def test_abs_sign_known() -> None:
    assert refine(Abs(x), Q.positive(x)) == x
    assert refine(Abs(x), Q.negative(x)) == -x
    assert refine(Abs(x), Q.nonnegative(x)) == x


def test_abs_unchanged() -> None:
    assert refine(Abs(x)) == Abs(x)
    assert refine(Abs(x), Q.complex(x)) == Abs(x)
    assert refine(Abs(x), Q.real(x)) == Abs(x)


def test_abs_mul_split() -> None:
    assert refine(Abs(x * y), Q.positive(x)) == x * Abs(y)
    assert refine(Abs(x * y * z), Q.positive(x)) == x * Abs(y * z)
    assert refine(Abs(x * y), Q.positive(x) & Q.positive(y)) == x * y


def test_abs_add_sign_path() -> None:
    assert refine(Abs(x + y), Q.positive(x) & Q.positive(y)) == x + y
    assert refine(Abs(x - y), Q.positive(x) & Q.negative(y)) == x - y
    assert refine(Abs(x + y), Q.negative(x) & Q.negative(y)) == -x - y


def test_abs_none_safety() -> None:
    with use_ask(stub_ask({})):
        assert refine(Abs(x), Q.zero(x)) == Abs(x)
        assert refine(Abs(x)) == Abs(x)

    # Zero unknown but positive known: still the vendored positive behavior.
    fake = stub_ask({str(Q.zero(x)): None, str(Q.real(x)): True,
                     str(Q.negative(x)): False})
    with use_ask(fake):
        assert refine(Abs(x), Q.positive(x)) == x

    fake, queries = scripted_ask([None, None, None])
    with use_ask(fake):
        assert refine(Abs(x)) == Abs(x)
    assert queries[0][0] == Q.zero(x)


def test_abs_numeric_oracle() -> None:
    assert_refinement_valid(Abs(x), Q.zero(x), refine(Abs(x), Q.zero(x)))
    assert_refinement_valid(Abs(x), Q.positive(x), refine(Abs(x), Q.positive(x)))
    assert_refinement_valid(Abs(x), Q.negative(x), refine(Abs(x), Q.negative(x)))
    assert_refinement_valid(
        Abs(x + y),
        Q.positive(x) & Q.positive(y),
        refine(Abs(x + y), Q.positive(x) & Q.positive(y)),
    )
    assert_refinement_valid(
        Abs(x * y) * z,
        Q.positive(x) & Q.real(z),
        refine(Abs(x * y) * z, Q.positive(x) & Q.real(z)),
    )


def test_abs_reference_ask_shared_cases() -> None:
    assert_refines_like_sympy(Abs(x), Q.positive(x))
    assert_refines_like_sympy(Abs(x), Q.negative(x))
    assert_refines_like_sympy(Abs(x), Q.nonnegative(x))
    assert_refines_like_sympy(Abs(x * y), Q.positive(x))
    assert_refines_like_sympy(Abs(x + y), Q.positive(x) & Q.positive(y))


def test_abs_documented_divergence() -> None:
    # Pinned SymPy returns x for a zero argument (the vendored handler never
    # asks Q.zero); we return 0.
    assert sympy_refine(Abs(x), Q.zero(x)) == x
    assert refine(Abs(x), Q.zero(x)) == S.Zero
