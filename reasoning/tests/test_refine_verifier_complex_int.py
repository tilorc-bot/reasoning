"""Adversarial verifier tests for the complex/log/pow, integer/combinatorial and
special/MinMax/delta refine handlers.

Written by an independent verifier (not the implementer).  The package tests
already cover the happy paths; these tests attack scope, fidelity, soundness,
robustness and termination, and record every counterexample or boundary
artifact found.  Expected-failure tests are ``strict=True`` xfails with the
reason spelled out.

Scope of the three packages under verification:

* ``log``, ``conjugate`` (+ the auxiliary ``Mul`` key), ``pow``, ``abs``,
  ``sign``, ``arg``;
* ``frac``, ``mod``, ``rem``, ``factorial``, ``binomial``, ``rf_ff``;
* ``special_gamma``, ``minmax_min``, ``minmax_max``, ``dirac_delta``,
  ``kronecker_delta``.
"""
from __future__ import annotations

import ast
import pathlib
from typing import Any

import pytest
from sympy.assumptions import Q
from sympy.assumptions.ask import ask as sympy_ask
from sympy.assumptions.refine import refine as sympy_refine
from sympy.abc import i, j, k, m, n, p, q, w, x, y, z
from sympy.core import S, Pow, Rational
from sympy.core.mod import Mod
from sympy.core.numbers import I, nan, oo, pi, zoo
from sympy.core.symbol import Symbol
from sympy.functions.combinatorial.factorials import (
    FallingFactorial,
    RisingFactorial,
    binomial,
    factorial,
)
from sympy.functions.elementary.complexes import Abs, arg, conjugate, im, re, sign
from sympy.functions.elementary.exponential import exp, log
from sympy.functions.elementary.integers import ceiling, floor, frac
from sympy.functions.elementary.miscellaneous import Max, Min, Rem, sqrt
from sympy.functions.elementary.piecewise import Piecewise
from sympy.functions.elementary.trigonometric import atan2, cos, sin
from sympy.functions.special.delta_functions import DiracDelta, Heaviside
from sympy.functions.special.gamma_functions import gamma
from sympy.functions.special.tensor_functions import KroneckerDelta
from sympy.matrices.expressions.matexpr import MatrixSymbol

from reasoning.refine import _upstream, refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    assert_refines_like_sympy,
    reference_ask,
    recording_ask,
    scripted_ask,
    stub_ask,
    use_ask,
)

INTEGERS = [0, 1, -1, 2, -2, 3, -3, 4, -4]
NONZERO_INTEGERS = [1, -1, 2, -2, 3, -3]
REALS = [0, 1, -1, 2, -2, S.Half, Rational(-1, 2), Rational(4, 3)]

# Registry key -> expected owning module (report sections 3.3/3.4/3.5/3.6/3.7/
# 3.9/3.12).  ``Mul`` is the documented auxiliary key of ``conjugate.py``.
IN_SCOPE_OWNERS: dict[str, str] = {
    "log": "log",
    "conjugate": "conjugate",
    "Mul": "conjugate",
    "Pow": "pow",
    "Abs": "abs",
    "sign": "sign",
    "arg": "arg",
    "frac": "frac",
    "Mod": "mod",
    "Rem": "rem",
    "factorial": "factorial",
    "binomial": "binomial",
    "RisingFactorial": "rf_ff",
    "FallingFactorial": "rf_ff",
    "gamma": "special_gamma",
    "Min": "minmax_min",
    "Max": "minmax_max",
    "DiracDelta": "dirac_delta",
    "KroneckerDelta": "kronecker_delta",
}


# ---------------------------------------------------------------------------
# 1. Scope: one registration per key, expected owner, no vendored-dict clash
# ---------------------------------------------------------------------------


def test_scope_every_key_registered_exactly_once() -> None:
    hdir = pathlib.Path(__file__).resolve().parents[1] / "refine" / "handlers"
    owners: dict[str, str] = {}
    for path in sorted(hdir.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "handlers_dict"
                and isinstance(node.ctx, ast.Store)
            ):
                key = ast.literal_eval(node.slice)
                assert key not in owners, (
                    f"duplicate registry key {key!r}: "
                    f"{owners.get(key)} and {path.name}"
                )
                owners[key] = path.name
    for key, module in IN_SCOPE_OWNERS.items():
        assert owners.get(key) == module + ".py", (
            f"{key} registered by {owners.get(key)!r}, expected {module}.py"
        )


def test_scope_runtime_handler_comes_from_expected_module() -> None:
    for key, module in IN_SCOPE_OWNERS.items():
        handler = _upstream.handlers_dict[key]
        assert handler.__module__ == f"reasoning.refine.handlers.{module}", (
            f"{key} resolves to {handler.__module__}"
        )


def test_scope_vendored_handler_names_are_overridden_not_duplicated() -> None:
    # The vendored dict must still exist unchanged in size for the keys no
    # handler module overrides; the overridden ones resolve to the new modules.
    vendored = {
        "Abs",
        "Pow",
        "atan2",
        "re",
        "im",
        "arg",
        "sign",
        "MatrixElement",
        "cos",
        "sin",
        "exp",
        "Heaviside",
        "floor",
        "ceiling",
    }
    assert vendored <= set(_upstream.handlers_dict)
    assert _upstream.handlers_dict["atan2"].__module__ == "reasoning.refine._upstream"
    assert _upstream.handlers_dict["exp"].__module__ == "reasoning.refine._upstream"


# ---------------------------------------------------------------------------
# 2. Fidelity: unrelated vendored behavior still matches upstream
# ---------------------------------------------------------------------------

# Broad corpus taken from reasoning/tests/test_refine.py plus the shared cases
# of the new handler tests.  All of these must refine exactly like SymPy under
# reference ask; intentional divergences are asserted separately below.
_SYMPY_MATCHING_CASES: list[tuple[Any, Any]] = [
    (Abs(x), Q.positive(x)),
    (1 + Abs(x), Q.positive(x)),
    (Abs(x), Q.negative(x)),
    (1 + Abs(x), Q.negative(x)),
    (Abs(x**2), True),
    (Abs(x**2), Q.real(x)),
    ((-1) ** x, Q.even(x)),
    ((-1) ** x, Q.odd(x)),
    ((-2) ** x, Q.even(x)),
    (sqrt(x**2), True),
    (sqrt(x**2), Q.complex(x)),
    (sqrt(x**2), Q.real(x)),
    (sqrt(x**2), Q.positive(x)),
    ((x**3) ** Rational(1, 3), True),
    ((x**3) ** Rational(1, 3), Q.positive(x)),
    (sqrt(1 / x), Q.real(x)),
    (sqrt(1 / x), Q.positive(x)),
    ((-1) ** (x + y), Q.even(x)),
    ((-1) ** (x + y + z), Q.odd(x) & Q.odd(z)),
    ((-1) ** (x + y + 1), Q.odd(x)),
    ((-1) ** (x + y + 2), Q.odd(x)),
    ((-1) ** (x + 3), True),
    ((-1) ** ((-1) ** x / 2 - S.Half), Q.integer(x)),
    ((-1) ** ((-1) ** x / 2 + S.Half), Q.integer(x)),
    ((-1) ** ((-1) ** x / 2 + 5 * S.Half), Q.integer(x)),
    ((-1) ** ((-1) ** x / 2 - 7 * S.Half), Q.integer(x)),
    ((-1) ** ((-1) ** x / 2 - 9 * S.Half), Q.integer(x)),
    (Abs(x) ** 2, Q.real(x)),
    (Abs(x) ** 3, Q.real(x)),
    (Abs(x) ** 2, True),
    (exp(pi * I * 2 * x), Q.integer(x)),
    (exp(pi * I * x), Q.even(x)),
    (exp(pi * I * 2 * (x + S.Half)), Q.integer(x)),
    (exp(pi * I * x), Q.odd(x)),
    (exp(pi * I * 2 * (x + Rational(1, 4))), Q.integer(x)),
    (exp(pi * I * (x + Rational(1, 2))), Q.even(x)),
    (exp(pi * I * (x + Rational(1, 2))), Q.integer(x)),
    (exp(2 * pi * I * (x + y + Rational(1, 4))), Q.integer(x) & Q.integer(y)),
    (Pow(S.Exp1, pi * I * 2 * x, evaluate=False), Q.integer(x)),
    (Pow(S.Exp1, pi * I * x, evaluate=False), Q.integer(x)),
    (re(x), Q.real(x)),
    (re(x), Q.imaginary(x)),
    (re(x + y), Q.real(x) & Q.real(y)),
    (re(x + y), Q.real(x) & Q.imaginary(y)),
    (re(x * y), Q.real(x) & Q.real(y)),
    (re(x * y), Q.real(x) & Q.imaginary(y)),
    (re(x * y * z), Q.real(x) & Q.real(y) & Q.real(z)),
    (im(x), Q.imaginary(x)),
    (im(x), Q.real(x)),
    (im(x + y), Q.imaginary(x) & Q.imaginary(y)),
    (im(x + y), Q.real(x) & Q.imaginary(y)),
    (im(x * y), Q.imaginary(x) & Q.real(y)),
    (im(x * y), Q.imaginary(x) & Q.imaginary(y)),
    (im(1 / x), Q.imaginary(x)),
    (im(x * y * z), Q.imaginary(x) & Q.imaginary(y) & Q.imaginary(z)),
    (re(1 / (x + I * y)), Q.real(x) & Q.real(y)),
    (im(1 / (x + I * y)), Q.real(x) & Q.real(y)),
    (
        re((w + I * x) * (y + I * z)),
        Q.real(w) & Q.real(x) & Q.real(y) & Q.real(z),
    ),
    (
        im((w + I * x) * (y + I * z)),
        Q.real(w) & Q.real(x) & Q.real(y) & Q.real(z),
    ),
    (arg(x), Q.positive(x)),
    (arg(x), Q.negative(x)),
    (arg(x), Q.real(x)),
    (Abs(x * y), Q.positive(x)),
    (Abs(x * y * z), Q.positive(x)),
    (cos(n * pi / 2), Q.odd(n)),
    (cos(n * pi), Q.even(n)),
    (cos(n * pi), Q.odd(n)),
    (sin(n * pi), Q.integer(n)),
    (sin(n * pi / 2), Q.odd(n) & Q.even((n - 1) / 2)),
    (sin(n * pi / 2), Q.odd(n) & Q.odd((n - 1) / 2)),
    (cos(n * pi), Q.integer(n)),
    (sin(n * pi / 2), Q.even(n)),
    (cos(n * pi / 2), Q.even(n)),
    (sin(n * pi / 2), Q.odd(n)),
    (cos(n * pi / 2), Q.odd(n)),
    (sin(x + n * pi), Q.integer(n)),
    (cos(x + n * pi), Q.integer(n)),
    (sin(x + n * pi), Q.even(n)),
    (cos(x + n * pi), Q.even(n)),
    (sin(x + n * pi), Q.odd(n)),
    (cos(x + n * pi), Q.odd(n)),
    (sin(x - n * pi), Q.odd(n)),
    (cos(x - n * pi), Q.even(n)),
    (sin(x + n * pi / 2), Q.even(n)),
    (cos(x + n * pi / 2), Q.even(n)),
    (sin(x + n * pi / 2), Q.odd(n)),
    (cos(x + n * pi / 2), Q.odd(n)),
    (sin(x - n * pi / 2), Q.odd(n)),
    (cos(x - n * pi / 2), Q.even(n)),
    (sin(x + y + 2 * n * pi), Q.integer(n)),
    (cos(x + y + 2 * n * pi), Q.integer(n)),
    (sin(x + n * pi), Q.zero(n)),
    (sin(x + n * pi), Q.zero(-n)),
    (cos(x + n * pi / 2), Q.integer(n)),
    (cos(x + y + n * pi / 2), Q.integer(n)),
    (cos(x + n * pi + m * pi / 2), Q.integer(n) & Q.even(m)),
    (cos(x + n * pi + m * pi / 2), Q.integer(n) & Q.odd(m)),
    (cos(x + n * pi + m * pi / 2), Q.integer(n) & Q.integer(m)),
    (cos(x + (2 * n + 1) * pi + m * pi / 2), Q.integer(n) & Q.integer(m)),
    (sin(x - (2 * n) * pi + m * pi / 2), Q.integer(n) & Q.integer(m)),
    (
        cos(x + n * pi + k * pi / 2 + m * pi / 2),
        Q.integer(n) & Q.odd(k) & Q.integer(m),
    ),
    (
        sin(x + n * pi + k * pi / 2 + m * pi / 2),
        Q.integer(n) & Q.odd(k) & Q.integer(m),
    ),
    (
        cos(x + n * pi / 2 + k * pi / 2 + m * pi / 2),
        Q.odd(n) & Q.odd(k) & Q.integer(m),
    ),
    (cos(x), Q.zero(x)),
    (sin(x), Q.zero(x)),
    (sin(x), Q.infinite(x) & Q.extended_real(x)),
    (cos(x), Q.infinite(x) & Q.extended_real(x)),
    (sin(x), Q.infinite(x)),
    (cos(x), Q.infinite(x)),
    (floor(x), Q.integer(x)),
    (ceiling(x), Q.integer(x)),
    (floor(x), Q.infinite(x)),
    (ceiling(x), Q.infinite(x)),
    (floor(y), Q.real(y)),
    (ceiling(y), Q.real(y)),
    (floor(x + y), Q.integer(x)),
    (ceiling(x + y), Q.integer(x)),
    (floor(x + y + z), Q.integer(x) & Q.integer(y)),
    (ceiling(x + y + z), Q.integer(x) & Q.integer(z)),
    (floor(x + y - z), True),
    (ceiling(ceiling(x) + y + floor(z)), True),
    (floor(floor(x) + floor(y)), True),
    (ceiling(ceiling(x) - ceiling(y)), True),
    # shared new-handler cases that agree with SymPy
    (Abs(x), Q.nonnegative(x)),
    (Abs(x * y), Q.positive(x) & Q.positive(y)),
    (Abs(x + y), Q.positive(x) & Q.positive(y)),
    (Abs(x - y), Q.positive(x) & Q.negative(y)),
    (Abs(x + y), Q.negative(x) & Q.negative(y)),
    (sign(x), Q.zero(x)),
    (sign(x), Q.real(x)),
    (sign(Abs(x)), Q.nonzero(x)),
    (sign(x), Q.imaginary(x)),
    (gamma(n), Q.positive(n)),
    (Min(x, y), Q.real(x) & Q.real(y)),
    (Max(x, y), Q.real(x) & Q.real(y)),
    (DiracDelta(x), Q.real(x)),
    (KroneckerDelta(n, m), Q.integer(n) & Q.integer(m)),
    (conjugate(x), Q.complex(x)),
    (sqrt(x**4), Q.real(x)),
    ((x**3) ** Rational(1, 2), Q.positive(x)),
    ((x**3) ** Rational(1, 3), Q.positive(x)),
    (exp(pi * I * x), Q.integer(x)),
    # vendored atan2 / Heaviside / floor / ceiling and Boolean-hook behavior
    (atan2(y, x), Q.real(y) & Q.positive(x)),
    (atan2(y, x), Q.negative(y) & Q.negative(x)),
    (atan2(y, x), Q.positive(y) & Q.negative(x)),
    (atan2(y, x), Q.zero(y) & Q.negative(x)),
    (atan2(y, x), Q.positive(y) & Q.zero(x)),
    (atan2(y, x), Q.zero(y) & Q.zero(x)),
    (Heaviside(x), Q.positive(x)),
    (Heaviside(x), Q.negative(x)),
    (Heaviside(x), Q.zero(x)),
    (Heaviside(x), Q.nonnegative(x)),
    (Heaviside(x, 1), Q.zero(x)),
    (Piecewise((1, x < 0), (3, True)), x < 0),
    (Piecewise((1, x < 0), (3, True)), ~(x < 0)),
    (Piecewise((1, x < 0), (3, True)), y < 0),
    (Piecewise((1, x > 0), (3, True)), x > 0),
    (Piecewise((1, x <= 0), (3, True)), x <= 0),
    (Piecewise((1, x >= 0), (3, True)), x >= 0),
    (Piecewise((1, x < 0), (0, True)), Q.positive(x)),
    (Piecewise((1, x < 0), (0, True)), Q.negative(x)),
]


def test_reference_ask_matches_upstream_on_broad_corpus() -> None:
    for expr, assumptions in _SYMPY_MATCHING_CASES:
        assert_refines_like_sympy(expr, assumptions)


def test_reference_ask_matrixelement_vendored_behavior() -> None:
    mat = MatrixSymbol("mat", 3, 3)
    assert_refines_like_sympy(mat[0, 1], Q.symmetric(mat))
    assert_refines_like_sympy(mat[1, 0], Q.symmetric(mat))
    assert_refines_like_sympy(mat[0, 1], Q.real(mat))


# Quoted expected outputs from the report / referenced upstream PRs.  These
# must hold with SymPy's ask bound (the handler logic oracle).
_REFERENCE_QUOTED_CASES: list[tuple[Any, Any, Any]] = [
    (log(exp(x)), Q.real(x), x),
    (log(x**2), Q.positive(x), 2 * log(x)),
    (log(x**y), Q.positive(x) & Q.real(y), y * log(x)),
    (log(1 / x), Q.positive(x), -log(x)),
    (log(x * y), Q.positive(x) & Q.positive(y), log(x) + log(y)),
    (log(x**2), Q.real(x), log(x**2)),
    (log(exp(x)), Q.imaginary(x), log(exp(x))),
    (conjugate(x), Q.real(x), x),
    (conjugate(x), Q.imaginary(x), -x),
    (conjugate(x**n), Q.imaginary(x) & Q.integer(n), (-x) ** n),
    (1 + conjugate(x), Q.real(x), 1 + x),
    (conjugate(x * y), Q.real(x) & Q.imaginary(y), -x * y),
    (z * conjugate(z), True, Abs(z) ** 2),
    (Abs(x), Q.zero(x), S.Zero),
    (sign(x), Q.positive(x), S.One),
    (sign(x), Q.negative(x), S.NegativeOne),
    (arg(x), Q.zero(x), nan),
    (arg(x), Q.imaginary(x) & Q.positive(im(x)), pi / 2),
    (arg(x), Q.imaginary(x) & Q.negative(im(x)), -pi / 2),
    ((x**3) ** Rational(1, 2), Q.real(x), (x**3) ** Rational(1, 2)),
    ((x**3) ** Rational(1, 3), Q.positive(x), x),
    (Abs(z) ** 2, Q.imaginary(z), -(z**2)),
    (Abs(z) ** 4, Q.imaginary(z), z**4),
    (Abs(z) ** 6, Q.imaginary(z), -(z**6)),
    (frac(x), Q.integer(x), S.Zero),
    (frac(x + n), Q.integer(n), frac(x)),
    (Mod(p, 1), Q.integer(p), S.Zero),
    (Mod(p, q), Q.integer(p) & Q.integer(q), p - q * floor(p / q)),
    (Mod(p, 2), Q.even(p), S.Zero),
    (Mod(p, 2), Q.odd(p), S.One),
    (
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.positive(q),
        p - q * floor(p / q),
    ),
    (
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.negative(q),
        p - q * ceiling(p / q),
    ),
    (
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.positive(q),
        p - q * ceiling(p / q),
    ),
    (
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonpositive(p) & Q.negative(q),
        p - q * floor(p / q),
    ),
    (factorial(n), Q.zero(n), S.One),
    (factorial(n), Q.eq(n, 1), S.One),
    (factorial(n), Q.integer(n) & Q.negative(n), zoo),
    (factorial(n), Q.positive_infinite(n), oo),
    (binomial(n, k), Q.zero(k), S.One),
    (binomial(n, k), Q.eq(k, 1), n),
    (binomial(n, k), Q.integer(k) & Q.negative(k), S.Zero),
    (
        binomial(n, k),
        Q.integer(n) & Q.nonnegative(n) & Q.integer(k) & Q.negative(n - k),
        S.Zero,
    ),
    (RisingFactorial(x, k), Q.zero(k), S.One),
    (FallingFactorial(x, k), Q.zero(k), S.One),
    (
        RisingFactorial(x, k),
        Q.zero(x) & Q.integer(k) & Q.positive(k),
        S.Zero,
    ),
    (FallingFactorial(n, n), Q.integer(n), factorial(n)),
    (gamma(n), Q.integer(n) & Q.nonpositive(n), zoo),
    (Min(x, y), Q.le(x, y), x),
    (Min(x, y), Q.ge(x, y), y),
    (Min(x, 0), Q.positive(x), S.Zero),
    (Min(x, y, z), Q.le(x, y) & Q.le(x, z), x),
    (Max(x, y), Q.ge(x, y), x),
    (Max(x, y), Q.le(x, y), y),
    (Max(x, 0), Q.negative(x), S.Zero),
    (DiracDelta(x), Q.nonzero(x), S.Zero),
    (KroneckerDelta(n, k), Q.eq(n, k), S.One),
    (KroneckerDelta(n, k), Q.ne(n, k), S.Zero),
]


def test_reference_ask_quoted_rules() -> None:
    with reference_ask():
        for expr, assumptions, expected in _REFERENCE_QUOTED_CASES:
            got = refine(expr, assumptions)
            assert got == expected, (
                f"refine({expr}, {assumptions}) == {got}, expected {expected}"
            )


# ---------------------------------------------------------------------------
# 3. Intentional divergences are correct (not just different)
# ---------------------------------------------------------------------------


def test_pow_nested_bugfix_is_the_correct_side() -> None:
    # SymPy still applies the wrong unconditional rewrite (issue #29684).
    assert (
        sympy_refine((x**3) ** Rational(1, 2), Q.real(x))
        == Abs(x) ** Rational(3, 2)
    )
    assert (
        sympy_refine((x**3) ** Rational(1, 3), Q.real(x)) == Abs(x)
    )
    # Local leaves them alone; the numeric oracle agrees with the original.
    refined = refine((x**3) ** Rational(1, 2), Q.real(x))
    assert refined == sqrt(x**3)
    assert refined != Abs(x) ** Rational(3, 2)
    assert_refinement_valid((x**3) ** Rational(1, 2), Q.real(x), refined)
    refined3 = refine((x**3) ** Rational(1, 3), Q.real(x))
    assert refined3 == (x**3) ** Rational(1, 3)
    assert refined3 != Abs(x)
    assert_refinement_valid((x**3) ** Rational(1, 3), Q.real(x), refined3)
    # SymPy's answers are numerically wrong at negative bases.
    assert (
        (x**3) ** Rational(1, 2)
    ).subs(x, -2) != (Abs(x) ** Rational(3, 2)).subs(x, -2)
    assert ((x**3) ** Rational(1, 3)).subs(x, -1) != Abs(x).subs(x, -1)


def test_abs_zero_and_sign_assumptions_divergences() -> None:
    assert sympy_refine(Abs(x), Q.zero(x)) == x
    assert refine(Abs(x), Q.zero(x)) is S.Zero
    assert sympy_refine(sign(x), Q.positive(x)) == sign(x)
    assert refine(sign(x), Q.positive(x)) is S.One
    assert sympy_refine(arg(x), Q.zero(x)) == arg(x)
    assert refine(arg(x), Q.zero(x)) is nan
    assert (
        sympy_refine(arg(x), Q.imaginary(x) & Q.positive(im(x))) == arg(x)
    )
    assert refine(arg(x), Q.imaginary(x) & Q.positive(im(x))) == pi / 2
    assert sympy_refine(Abs(z) ** 2, Q.imaginary(z)) == Abs(z) ** 2
    assert refine(Abs(z) ** 2, Q.imaginary(z)) == -(z**2)


# ---------------------------------------------------------------------------
# 4. Soundness: numeric oracle with adversarial samples
# ---------------------------------------------------------------------------


def test_nested_power_oracle_adversarial() -> None:
    cases: list[tuple[Any, Any, dict[Any, list[Any]]]] = [
        (
            (x**3) ** Rational(1, 2),
            Q.real(x),
            {x: [-2, -1, 0, 1, 2, S.Half, Rational(4, 3), Rational(-4, 3)]},
        ),
        (
            (x**3) ** Rational(1, 3),
            Q.real(x),
            {x: [-2, -1, 0, 1, 2, S.Half, Rational(-1, 2)]},
        ),
        (
            (x**2) ** Rational(1, 2),
            Q.real(x),
            {x: [-2, -1, 0, 1, 2, I, 1 + I, S.Half]},
        ),
        (
            (x**2) ** Rational(1, 3),
            Q.real(x),
            {x: [-2, -1, 0, 1, 2]},
        ),
        (
            (x**4) ** Rational(1, 2),
            Q.real(x),
            {x: [-2, -1, 0, 1, 2, S.Half]},
        ),
        (
            (x ** (-2)) ** Rational(1, 2),
            Q.real(x) & Q.nonzero(x),
            {x: [-2, -1, 1, 2, S.Half]},
        ),
        (
            (x**y) ** z,
            Q.positive(x) & Q.real(y),
            {
                x: [1, 2, 3, S.Half],
                y: [-2, -1, 0, Rational(1, 3), 1, 2],
                z: [-2, -1, S.Half, 0, 1, 2, I, 1 + I],
            },
        ),
        (
            (x**y) ** z,
            Q.real(x) & Q.even(y),
            {
                x: [-2, -1, 0, 1, 2, S.Half],
                y: [-2, 0, 2, 4],
                z: [-2, -1, S.Half, 0, 1, 2, I],
            },
        ),
        (
            (x**y) ** z,
            Q.integer(z),
            {
                x: [-2, -1, 0, 1, 2, I, 1 + I],
                y: [-2, S.Half, 1, 2, I],
                z: [-2, -1, 0, 1, 2],
            },
        ),
    ]
    for expr, assumptions, values in cases:
        assert_refinement_valid(expr, assumptions, refine(expr, assumptions), values=values)


def test_abs_power_imaginary_oracle_adversarial() -> None:
    for exponent in (2, 4, 6, -2):
        expr = Abs(z) ** exponent
        refined = refine(expr, Q.imaginary(z))
        assert_refinement_valid(
            expr, Q.imaginary(z), refined, values={z: [I, -I, 2 * I, -3 * I]}
        )
    expr = Abs(z) ** (2 * n)
    assumptions = Q.imaginary(z) & Q.integer(n)
    assert_refinement_valid(
        expr,
        assumptions,
        refine(expr, assumptions),
        values={z: [I, -I, 2 * I], n: [-2, -1, 0, 1, 2]},
    )
    assert refine(Abs(z) ** 3, Q.imaginary(z)) == Abs(z) ** 3


def test_log_branch_cut_oracle_adversarial() -> None:
    cases: list[tuple[Any, Any, dict[Any, list[Any]]]] = [
        (
            log(exp(x)),
            Q.real(x),
            {x: [-3, -1, 0, 1, 3, pi, -pi, S.Half, Rational(4, 3)]},
        ),
        (
            log(x**2),
            Q.positive(x),
            {x: [1, 2, 3, S.Half, Rational(4, 3), sqrt(2)]},
        ),
        (
            log(x**y),
            Q.positive(x) & Q.real(y),
            {
                x: [1, 2, 3, S.Half],
                y: [-2, -1, 0, Rational(1, 3), 1, 2],
            },
        ),
        (
            log(x * y),
            Q.positive(x) & Q.positive(y),
            {x: [1, 2, S.Half], y: [1, 3, Rational(3, 2)]},
        ),
        (
            log(1 / x),
            Q.positive(x),
            {x: [1, 2, S.Half]},
        ),
    ]
    for expr, assumptions, values in cases:
        assert_refinement_valid(expr, assumptions, refine(expr, assumptions), values=values)
    # Branch-cut guard: log(x**2) stays put for real x (negative samples!).
    refined = refine(log(x**2), Q.real(x))
    assert refined == log(x**2)
    assert_refinement_valid(
        log(x**2), Q.real(x), refined, values={x: [-2, -1, 1, 2, S.Half]}
    )
    assert refine(log(exp(x)), Q.imaginary(x)) == log(exp(x))


def test_conjugate_oracle_adversarial() -> None:
    assert_refinement_valid(
        conjugate(x), Q.real(x), refine(conjugate(x), Q.real(x)),
        values={x: [-2, -1, 0, 1, 2, S.Half, Rational(4, 3)]},
    )
    assert_refinement_valid(
        conjugate(x), Q.imaginary(x), refine(conjugate(x), Q.imaginary(x)),
        values={x: [I, -I, 2 * I, -3 * I]},
    )
    expr = conjugate(x**n)
    assumptions = Q.imaginary(x) & Q.integer(n)
    assert_refinement_valid(
        expr, assumptions, refine(expr, assumptions),
        values={x: [I, -I, 2 * I], n: [-2, -1, 0, 1, 2]},
    )
    assumptions = Q.complex(x) & Q.integer(n)
    assert_refinement_valid(
        expr, assumptions, refine(expr, assumptions),
        values={x: [I, 1 + I, -2, S.Half, 0], n: [-2, -1, 0, 1, 2]},
    )
    pair = z * conjugate(z)
    assert_refinement_valid(
        pair, True, refine(pair), values={z: [I, 1 + I, 1 - I, -2, S.Half, 0]}
    )
    assert_refinement_valid(
        2 * z * conjugate(z) * y, True, refine(2 * z * conjugate(z) * y),
        values={z: [I, 1 + I, -2], y: [1, 2, I]},
    )


def test_abs_oracle_adversarial() -> None:
    assert_refinement_valid(
        Abs(x), Q.zero(x), refine(Abs(x), Q.zero(x)), values={x: [0]}
    )
    assert_refinement_valid(
        Abs(x), Q.positive(x), refine(Abs(x), Q.positive(x)),
        values={x: [1, 2, S.Half]},
    )
    assert_refinement_valid(
        Abs(x), Q.negative(x), refine(Abs(x), Q.negative(x)),
        values={x: [-1, -2, Rational(-1, 2)]},
    )
    for expr, assumptions, values in (
        (Abs(x + y), Q.positive(x) & Q.positive(y), {x: [1, 2], y: [1, 3]}),
        (Abs(x - y), Q.positive(x) & Q.negative(y), {x: [1, 2], y: [-1, -3]}),
        (Abs(x + y), Q.negative(x) & Q.negative(y), {x: [-1, -2], y: [-1, -3]}),
        (Abs(x * y), Q.positive(x), {x: [1, 2], y: [I, -3, 1 + I]}),
        (Abs(x * y), Q.zero(x) & Q.finite(y), {x: [0], y: [-2, 0, 2]}),
    ):
        assert_refinement_valid(
            expr, assumptions, refine(expr, assumptions), values=values
        )


def test_sign_arg_oracle_adversarial() -> None:
    for expr, assumptions, values in (
        (sign(x), Q.positive(x), {x: [1, 2, S.Half]}),
        (sign(x), Q.negative(x), {x: [-1, -2, Rational(-1, 2)]}),
        (sign(x), Q.zero(x), {x: [0]}),
        (
            sign(z),
            Q.imaginary(z) & Q.positive(im(z)),
            {z: [I, 2 * I]},
        ),
        (
            sign(z),
            Q.imaginary(z) & Q.negative(im(z)),
            {z: [-I, -2 * I]},
        ),
        (arg(x), Q.positive(x), {x: [1, 2]}),
        (arg(x), Q.negative(x), {x: [-1, -2]}),
        (arg(x), Q.zero(x), {x: [0]}),
        (
            arg(z),
            Q.imaginary(z) & Q.positive(im(z)),
            {z: [I, 2 * I]},
        ),
        (
            arg(z),
            Q.imaginary(z) & Q.negative(im(z)),
            {z: [-I, -2 * I]},
        ),
    ):
        assert_refinement_valid(
            expr, assumptions, refine(expr, assumptions), values=values
        )


def test_integer_functions_oracle_adversarial() -> None:
    assert_refinement_valid(
        frac(x), Q.integer(x), refine(frac(x), Q.integer(x)),
        values={x: INTEGERS},
    )
    assert_refinement_valid(
        frac(x + n), Q.integer(n), refine(frac(x + n), Q.integer(n)),
        values={x: [-2, -1, S.Half, Rational(1, 3), 2], n: INTEGERS},
    )
    assert_refinement_valid(
        frac(x + y + n),
        Q.integer(n) & Q.integer(y),
        refine(frac(x + y + n), Q.integer(n) & Q.integer(y)),
        values={x: [S.Half, Rational(1, 3), -1], y: INTEGERS, n: INTEGERS},
    )
    assert_refinement_valid(
        Mod(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonzero(q),
        refine(Mod(p, q), Q.integer(p) & Q.integer(q) & Q.nonzero(q)),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )
    assert_refinement_valid(
        Mod(p, 2), Q.even(p), refine(Mod(p, 2), Q.even(p)), values={p: INTEGERS}
    )
    assert_refinement_valid(
        Mod(p, 2), Q.odd(p), refine(Mod(p, 2), Q.odd(p)), values={p: INTEGERS}
    )
    for p_sign, q_sign in (
        ("nonnegative", "positive"),
        ("nonpositive", "negative"),
        ("nonnegative", "negative"),
        ("nonpositive", "positive"),
    ):
        assumptions = (
            Q.integer(p)
            & Q.integer(q)
            & getattr(Q, p_sign)(p)
            & getattr(Q, q_sign)(q)
        )
        assert_refinement_valid(
            Rem(p, q),
            assumptions,
            refine(Rem(p, q), assumptions),
            values={p: INTEGERS, q: NONZERO_INTEGERS},
        )
    assert_refinement_valid(
        Rem(p, q),
        Q.integer(p) & Q.integer(q),
        refine(Rem(p, q), Q.integer(p) & Q.integer(q)),
        values={p: INTEGERS, q: NONZERO_INTEGERS},
    )


def test_factorial_binomial_oracle_adversarial() -> None:
    assert_refinement_valid(
        factorial(n), Q.zero(n), refine(factorial(n), Q.zero(n)), values={n: [0]}
    )
    assert_refinement_valid(
        factorial(n), Q.eq(n, 1), refine(factorial(n), Q.eq(n, 1)), values={n: [1]}
    )
    assert_refinement_valid(
        factorial(n),
        Q.integer(n) & Q.negative(n),
        refine(factorial(n), Q.integer(n) & Q.negative(n)),
        values={n: [-1, -2, -3, -4]},
    )
    assert_refinement_valid(
        factorial(n),
        Q.positive_infinite(n),
        refine(factorial(n), Q.positive_infinite(n)),
        values={n: [oo]},
    )
    assert_refinement_valid(
        binomial(n, k), Q.zero(k), refine(binomial(n, k), Q.zero(k)),
        values={n: INTEGERS, k: [0]},
    )
    assert_refinement_valid(
        binomial(n, k), Q.eq(k, 1), refine(binomial(n, k), Q.eq(k, 1)),
        values={n: INTEGERS, k: [1]},
    )
    assert_refinement_valid(
        binomial(n, k),
        Q.integer(k) & Q.negative(k),
        refine(binomial(n, k), Q.integer(k) & Q.negative(k)),
        values={n: INTEGERS + [S.Half], k: [-1, -2, -3]},
    )
    support = (
        Q.integer(n) & Q.nonnegative(n) & Q.integer(k) & Q.negative(n - k)
    )
    assert_refinement_valid(
        binomial(n, k), support, refine(binomial(n, k), support),
        values={n: INTEGERS, k: INTEGERS},
    )
    assert_refinement_valid(
        RisingFactorial(x, k), Q.zero(k),
        refine(RisingFactorial(x, k), Q.zero(k)),
        values={x: INTEGERS, k: [0]},
    )
    assert_refinement_valid(
        FallingFactorial(x, k), Q.zero(k),
        refine(FallingFactorial(x, k), Q.zero(k)),
        values={x: INTEGERS, k: [0]},
    )
    zero_base = Q.zero(x) & Q.integer(k) & Q.positive(k)
    assert_refinement_valid(
        RisingFactorial(x, k), zero_base,
        refine(RisingFactorial(x, k), zero_base),
        values={x: [0], k: [1, 2, 3, 4]},
    )
    assert_refinement_valid(
        FallingFactorial(x, k), zero_base,
        refine(FallingFactorial(x, k), zero_base),
        values={x: [0], k: [1, 2, 3, 4]},
    )
    assert_refinement_valid(
        FallingFactorial(n, n), Q.integer(n),
        refine(FallingFactorial(n, n), Q.integer(n)),
        values={n: [-3, -2, -1, 0, 1, 2, 3]},
    )
    assert_refinement_valid(
        gamma(n), Q.integer(n) & Q.nonpositive(n),
        refine(gamma(n), Q.integer(n) & Q.nonpositive(n)),
        values={n: [0, -1, -2, -3]},
    )


def test_minmax_oracle_adversarial() -> None:
    real_values = [-2, -1, 0, 1, 2, S.Half]
    for expr, assumptions in (
        (Min(x, y), Q.le(x, y)),
        (Min(x, y), Q.ge(x, y)),
        (Min(x, y), Q.lt(x, y)),
        (Min(x, y), Q.gt(x, y)),
        (Max(x, y), Q.le(x, y)),
        (Max(x, y), Q.ge(x, y)),
        (Max(x, y), Q.lt(x, y)),
        (Max(x, y), Q.gt(x, y)),
    ):
        assert_refinement_valid(
            expr, assumptions, refine(expr, assumptions),
            values={x: real_values, y: real_values},
        )
    # Equal values and the zero shortcuts.
    assert_refinement_valid(
        Min(x, y), Q.eq(x, y), refine(Min(x, y), Q.eq(x, y)),
        values={x: real_values, y: real_values},
    )
    for expr, assumptions, values in (
        (Min(x, 0), Q.positive(x), {x: [1, 2]}),
        (Min(x, 0), Q.zero(x), {x: [0]}),
        (Min(x, 0), Q.nonnegative(x), {x: [0, 1, 2]}),
        (Min(x, 0), Q.negative(x), {x: [-1, -2]}),
        (Max(x, 0), Q.positive(x), {x: [1, 2]}),
        (Max(x, 0), Q.zero(x), {x: [0]}),
        (Max(x, 0), Q.nonnegative(x), {x: [0, 1, 2]}),
        (Max(x, 0), Q.negative(x), {x: [-1, -2]}),
    ):
        assert_refinement_valid(
            expr, assumptions, refine(expr, assumptions), values=values
        )
    # Infinite arguments (explicit values; the default samples have none).
    for expr, assumptions, values in (
        (Min(x, y), Q.negative_infinite(x), {x: [-oo], y: [-2, 0, 2, oo]}),
        (Min(x, y), Q.positive_infinite(x), {x: [oo], y: [-2, 0, 2]}),
        (Max(x, y), Q.positive_infinite(x), {x: [oo], y: [-2, 0, 2, -oo]}),
        (Max(x, y), Q.negative_infinite(x), {x: [-oo], y: [-2, 0, 2]}),
    ):
        assert_refinement_valid(
            expr, assumptions, refine(expr, assumptions), values=values
        )
    assert refine(Min(x, y), Q.positive_infinite(x) & Q.positive_infinite(y)) is oo
    assert refine(Max(x, y), Q.negative_infinite(x) & Q.negative_infinite(y)) is -oo


def test_delta_oracle_adversarial() -> None:
    assert_refinement_valid(
        DiracDelta(x), Q.nonzero(x), refine(DiracDelta(x), Q.nonzero(x)),
        values={x: [-2, -1, 1, 2, S.Half]},
    )
    assert_refinement_valid(
        DiracDelta(x, 2), Q.nonzero(x),
        refine(DiracDelta(x, 2), Q.nonzero(x)),
        values={x: [-2, -1, 1, 2]},
    )
    assert refine(DiracDelta(x), Q.zero(x)) == DiracDelta(x)
    assert_refinement_valid(
        KroneckerDelta(i, j), Q.eq(i, j),
        refine(KroneckerDelta(i, j), Q.eq(i, j)),
        values={i: [0, 1, -1], j: [0, 1, -1]},
    )
    assert_refinement_valid(
        KroneckerDelta(i, j), Q.ne(i, j),
        refine(KroneckerDelta(i, j), Q.ne(i, j)),
        values={i: [0, 1, -1], j: [0, 1, -1]},
    )


# ---------------------------------------------------------------------------
# 5. Variables that do not satisfy the assumptions: unchanged
# ---------------------------------------------------------------------------


def test_unmet_assumptions_leave_expression_unchanged() -> None:
    cases: list[tuple[Any, Any]] = [
        # log: branch-cut guards and missing premises
        (log(exp(x)), True),
        (log(exp(x)), Q.imaginary(x)),
        (log(exp(x)), Q.complex(x)),
        (log(x**2), Q.real(x)),
        (log(x**2), Q.negative(x)),
        (log(x**y), Q.positive(x)),
        (log(x**y), Q.real(x) & Q.real(y)),
        (log(x * y), Q.positive(x)),
        (log(x * y), Q.negative(x) & Q.negative(y)),
        # conjugate
        (conjugate(x), True),
        (conjugate(x), Q.complex(x)),
        (conjugate(x**n), Q.integer(n)),
        (conjugate(x**n), Q.imaginary(x)),
        (conjugate(x * y), Q.complex(x) & Q.complex(y)),
        # Pow: no nested-power case applies
        ((x**y) ** z, True),
        ((x**y) ** z, Q.real(x) & Q.real(y)),
        ((x**y) ** z, Q.real(x) & Q.odd(y)),
        ((x**3) ** Rational(1, 3), Q.real(x)),
        (Abs(z) ** 2, True),
        (Abs(z) ** 3, Q.imaginary(z)),
        # Abs / sign / arg
        (Abs(x), Q.real(x)),
        (Abs(x), Q.complex(x)),
        (sign(x), True),
        (sign(x), Q.complex(x)),
        (sign(x), Q.imaginary(x)),
        (arg(x), True),
        (arg(x), Q.real(x)),
        (arg(z), Q.imaginary(z)),
        # integer functions
        (frac(x), Q.real(x)),
        (frac(x), Q.positive(x)),
        (frac(x + n), Q.real(n)),
        (Mod(p, q), Q.real(p) & Q.real(q)),
        (Mod(p, q), Q.integer(p)),
        (Mod(p, 2), Q.positive(p)),
        (Rem(p, q), Q.real(p) & Q.real(q)),
        (Rem(p, q), Q.integer(p) & Q.integer(q)),
        (Rem(p, q), Q.integer(p) & Q.nonnegative(p)),
        # factorial / binomial / rf / gamma
        (factorial(n), Q.real(n)),
        (factorial(n), Q.integer(n)),
        (factorial(n), Q.negative(n)),
        (binomial(n, k), Q.real(n) & Q.real(k)),
        (binomial(n, k), Q.integer(k)),
        (binomial(n, k), Q.integer(n) & Q.nonnegative(n)),
        (RisingFactorial(x, k), Q.zero(x)),
        (FallingFactorial(x, k), Q.zero(x)),
        (FallingFactorial(n, n), Q.real(n)),
        (gamma(n), Q.integer(n) & Q.positive(n)),
        (gamma(n), Q.real(n)),
        # Min / Max
        (Min(x, y), True),
        (Min(x, y), Q.real(x) & Q.real(y)),
        (Min(x, y), Q.positive(x) & Q.negative(y)),
        (Min(x, y), Q.eq(x, y)),
        (Min(x, y, z), Q.le(x, y)),
        (Min(x, y), Q.infinite(x)),
        (Max(x, y), True),
        (Max(x, y), Q.eq(x, y)),
        (Max(x, y, z), Q.ge(x, y)),
        (Max(x, y), Q.infinite(x)),
        # deltas
        (DiracDelta(x), Q.zero(x)),
        (DiracDelta(x), Q.real(x)),
        (DiracDelta(x, 2), Q.zero(x)),
        (KroneckerDelta(i, j), Q.eq(i, k)),
        (KroneckerDelta(i, j), Q.ne(i, k)),
        (KroneckerDelta(i, j), Q.real(i) & Q.real(j)),
    ]
    for expr, assumptions in cases:
        assert refine(expr, assumptions) == expr, (
            f"refine({expr}, {assumptions}) changed unexpectedly"
        )


def test_binomial_support_rule_needs_integer_k() -> None:
    # The report's quoted rule omitted Q.integer(k); without it the rule is
    # false (binomial(2, 3/2) = 16/(3*pi)), so no refinement may happen.
    assumptions = Q.integer(n) & Q.nonnegative(n) & Q.negative(n - k)
    assert refine(binomial(n, k), assumptions) == binomial(n, k)
    assert binomial(2, Rational(3, 2)) != 0


def test_rem_floor_identity_is_not_applied_without_signs() -> None:
    # Rem(p, q) = p - int(p/q)*q; with integer p, q but unknown signs neither
    # floor nor ceiling is implied.  The naive floor rewrite is numerically
    # false: Rem(-2, 3) = -2 but -2 - 3*floor(-2/3) = 1.
    assert refine(Rem(p, q), Q.integer(p) & Q.integer(q)) == Rem(p, q)
    assert Rem(-2, 3) == -2
    assert (-2 - 3 * floor(Rational(-2, 3))) == 1


# ---------------------------------------------------------------------------
# 6. Robustness: stub/scripted ask, no crash, no change on unknown
# ---------------------------------------------------------------------------

_QUERY_DEPENDENT_EXPRESSIONS: list[Any] = [
    log(exp(x)),
    log(x**2),
    log(x * y),
    conjugate(x),
    conjugate(x**n),
    (x**3) ** Rational(1, 2),
    (x**2) ** Rational(1, 2),
    Abs(z) ** 2,
    Abs(x),
    Abs(x * y),
    sign(x),
    sign(z),
    arg(x),
    arg(z),
    frac(x),
    frac(x + n),
    Mod(p, 1),
    Mod(p, 2),
    Mod(p, q),
    Rem(p, q),
    factorial(n),
    binomial(n, k),
    RisingFactorial(x, k),
    FallingFactorial(x, k),
    FallingFactorial(n, n),
    gamma(n),
    Min(x, y),
    Min(x, 0),
    Max(x, y),
    Max(x, 0),
    DiracDelta(x),
    KroneckerDelta(i, j),
]


def test_stub_none_never_changes_expression() -> None:
    with use_ask(stub_ask({})):
        for expr in _QUERY_DEPENDENT_EXPRESSIONS:
            assert refine(expr) == expr, f"{expr} changed with all-None ask"


def test_scripted_mixed_answers_do_not_raise() -> None:
    for expr in _QUERY_DEPENDENT_EXPRESSIONS:
        fake, _ = scripted_ask([None, True, False, None, True, False] * 4)
        with use_ask(fake):
            result = refine(expr)
        assert result is not None


def test_handlers_ask_through_the_upstream_module() -> None:
    # A recording stub must observe the queries: proves the monkeypatch reaches
    # the handlers (no from-import of ask) and that answers are respected.
    fake, log = recording_ask({str(Q.integer(x)): True})
    with use_ask(fake):
        assert refine(frac(x)) is S.Zero
    assert [entry[0] for entry in log] == [Q.integer(x)]

    fake, log = recording_ask({str(Q.zero(x)): True})
    with use_ask(fake):
        assert refine(Abs(x)) is S.Zero
    assert log and log[0][0] == Q.zero(x)


def test_nan_and_zoo_inputs_do_not_crash() -> None:
    for expr in (
        DiracDelta(nan),
        DiracDelta(zoo),
        factorial(nan),
        factorial(zoo),
        gamma(nan),
        gamma(zoo),
        frac(nan),
        frac(zoo),
        Mod(nan, 2),
        Rem(nan, 2),
        conjugate(nan),
        conjugate(zoo),
        Abs(nan),
        sign(nan),
        sign(zoo),
        arg(nan),
        arg(zoo),
        log(nan),
        log(zoo),
        binomial(nan, 2),
    ):
        assert refine(expr) == expr or expr.has(nan)


# ---------------------------------------------------------------------------
# 7. Termination / fixed point
# ---------------------------------------------------------------------------

_FIXED_POINT_CASES: list[tuple[Any, Any]] = [
    ((x**3) ** Rational(1, 2), Q.real(x)),
    ((x**3) ** Rational(1, 3), Q.real(x)),
    ((x**2) ** Rational(1, 2), Q.real(x)),
    ((x**y) ** z, Q.positive(x) & Q.real(y)),
    ((x**y) ** z, Q.real(x) & Q.even(y)),
    ((x**y) ** z, Q.integer(z)),
    (Abs(z) ** 2, Q.imaginary(z)),
    (Abs(z) ** (2 * n), Q.imaginary(z) & Q.integer(n)),
    (Pow(S.Exp1, x, evaluate=False), Q.even(x)),
    (Pow(S.Exp1, 2 * pi * I * x, evaluate=False), Q.integer(x)),
    (exp(pi * I * 2 * x), Q.integer(x)),
    (log(exp(x)), Q.real(x)),
    (log(x**2), Q.positive(x)),
    (log(1 / x), Q.positive(x)),
    (log(x * y), Q.positive(x) & Q.positive(y)),
    (log(x**y), Q.positive(x) & Q.real(y)),
    (conjugate(x), Q.real(x)),
    (conjugate(x), Q.imaginary(x)),
    (conjugate(x**n), Q.imaginary(x) & Q.integer(n)),
    (z * conjugate(z), True),
    (2 * z * conjugate(z) * y, True),
    (z * conjugate(z) * conjugate(y) * y, True),
    (conjugate(x * y), Q.real(x) & Q.imaginary(y)),
    (sign(x), Q.positive(x)),
    (sign(z), Q.imaginary(z) & Q.positive(im(z))),
    (arg(x), Q.negative(x)),
    (arg(x), Q.zero(x)),
    (Abs(x), Q.zero(x)),
    (Abs(x * y), Q.positive(x) & Q.positive(y)),
    (frac(x), Q.integer(x)),
    (frac(x + n), Q.integer(n)),
    (Mod(p, 1), Q.integer(p)),
    (Mod(p, q), Q.integer(p) & Q.integer(q)),
    (
        Rem(p, q),
        Q.integer(p) & Q.integer(q) & Q.nonnegative(p) & Q.positive(q),
    ),
    (factorial(n), Q.integer(n) & Q.negative(n)),
    (binomial(n, k), Q.zero(k)),
    (
        binomial(n, k),
        Q.integer(n) & Q.nonnegative(n) & Q.integer(k) & Q.negative(n - k),
    ),
    (RisingFactorial(x, k), Q.zero(k)),
    (FallingFactorial(n, n), Q.integer(n)),
    (gamma(n), Q.integer(n) & Q.nonpositive(n)),
    (Min(x, y), Q.le(x, y)),
    (Min(x, y, z), Q.le(x, y) & Q.le(x, z)),
    (Max(x, y), Q.ge(x, y)),
    (DiracDelta(x), Q.nonzero(x)),
    (KroneckerDelta(i, j), Q.eq(i, j)),
    (KroneckerDelta(i, j), Q.ne(i, j)),
]


def test_refine_reaches_a_fixed_point() -> None:
    for expr, assumptions in _FIXED_POINT_CASES:
        first = refine(expr, assumptions)
        second = refine(first, assumptions)
        third = refine(second, assumptions)
        assert first == second == third, (
            f"not a fixed point: {expr} under {assumptions}: "
            f"{first} -> {second} -> {third}"
        )


def test_pow_exp_forms_agree_and_terminate() -> None:
    for assumptions in (Q.integer(x), Q.even(x), Q.odd(x), Q.real(x), Q.zero(x)):
        for unevaluated in (
            Pow(S.Exp1, x, evaluate=False),
            Pow(S.Exp1, pi * I * x, evaluate=False),
            Pow(S.Exp1, 2 * pi * I * x, evaluate=False),
        ):
            result = refine(unevaluated, assumptions)
            assert refine(result, assumptions) == result
    assert (
        refine(Pow(S.Exp1, pi * I * 2 * x, evaluate=False), Q.integer(x))
        == refine(exp(pi * I * 2 * x), Q.integer(x))
        == 1
    )
    assert (
        refine(Pow(S.Exp1, pi * I * x, evaluate=False), Q.integer(x))
        == refine(exp(pi * I * x), Q.integer(x))
        == (-1) ** x
    )


# ---------------------------------------------------------------------------
# 8. The auxiliary ``Mul`` handler: no-op unless a conjugate pair matches
# ---------------------------------------------------------------------------


def test_mul_handler_is_noop_on_general_products() -> None:
    for expr in (
        x * y,
        x * conjugate(y),
        conjugate(x) * conjugate(y),
        conjugate(x) ** 2,
        x**2 * conjugate(x),
        2 * conjugate(x),
        x * y * z,
        (x + 1) * (conjugate(x) + 1),
    ):
        assert refine(expr) == expr, f"Mul handler changed {expr}"


def test_mul_handler_pairs_only_matching_conjugates() -> None:
    assert refine(x * conjugate(x)) == Abs(x) ** 2
    assert refine(2 * x * conjugate(x)) == 2 * Abs(x) ** 2
    assert refine(I * x * conjugate(x)) == I * Abs(x) ** 2
    assert refine(x * conjugate(x) * y * conjugate(y)) == (
        Abs(x) ** 2 * Abs(y) ** 2
    )
    assert refine(y * conjugate(x) * conjugate(y)) == conjugate(x) * Abs(y) ** 2
    assert refine(Abs(x) * x * conjugate(x)) == Abs(x) ** 3
    # The rule is assumption-free, so it fires even with an all-None ask.
    with use_ask(stub_ask({})):
        assert refine(x * conjugate(x)) == Abs(x) ** 2


def test_mul_handler_noncommutative_conjugate_pair() -> None:
    a = Symbol("a", commutative=False)
    assert refine(a * conjugate(a)) == a * conjugate(a)


# ---------------------------------------------------------------------------
# 9. Recorded boundary artifacts and engine limitations
# ---------------------------------------------------------------------------


def test_kronecker_reversed_assumption_order_is_a_local_gap() -> None:
    # Reference ask reverses Q.eq/Q.ne, the local engine does not, so the
    # symmetric spelling of the assumption leaves the delta unchanged.
    assert refine(KroneckerDelta(i, j), Q.eq(i, j)) is S.One
    assert refine(KroneckerDelta(i, j), Q.ne(i, j)) is S.Zero
    assert sympy_ask(Q.eq(j, i), Q.eq(i, j)) is True
    assert sympy_ask(Q.ne(j, i), Q.ne(i, j)) is True
    assert refine(KroneckerDelta(i, j), Q.eq(j, i)) == KroneckerDelta(i, j)


def test_nonzero_assumption_semantics_for_the_oracle() -> None:
    # Q.nonzero implies real (both engines); the harness numeric oracle's
    # nonzero check accepts I, so adversarial nonzero samples must be real.
    assert sympy_ask(Q.nonzero(I)) is False
    assert sympy_ask(Q.real(x), Q.nonzero(x)) is True
    assert refine(conjugate(x), Q.nonzero(x)) == x
    # nonzero does not imply nonnegative, so Abs is not simplified
    assert refine(Abs(x), Q.nonzero(x)) == Abs(x)
    assert refine(Abs(x), Q.positive(x)) == x


def test_boundary_zero_times_infinite_artifact() -> None:
    # Engine-level boundary artifact, shared with SymPy's ask: Q.zero(x)
    # implies Q.zero(x*y) without a finiteness guard, so at (x, y) = (0, oo)
    # the original Abs(x*y) is nan while the refined value is 0.  Recorded so
    # that an engine-level fix (or a handler-level finite guard) is noticed.
    assert sympy_ask(Q.zero(x * y), Q.zero(x) & Q.infinite(y)) is True
    assert refine(Abs(x * y), Q.zero(x) & Q.infinite(y)) is S.Zero
    assert (x * y).subs({x: 0, y: oo}).has(nan)
    # The same artifact appears in the query-free pair identity at z = zoo:
    assert refine(z * conjugate(z), Q.infinite(z)) == Abs(z) ** 2
    assert Abs(zoo) == oo


def test_inconsistent_assumptions_raise_pre_existing_engine_error() -> None:
    # Engine-level: satask raises ValueError for inconsistent assumptions and
    # the dispatcher propagates it.  This is reproducible with the vendored
    # Abs handler alone, i.e. it predates the new handlers.
    with pytest.raises(ValueError, match="Inconsistent assumptions"):
        refine(conjugate(x), Q.infinite(x) & Q.real(x))
    with pytest.raises(ValueError, match="Inconsistent assumptions"):
        refine(Abs(x), Q.positive(x) & Q.negative(x))
    with pytest.raises(ValueError, match="Inconsistent assumptions"):
        refine(gamma(n), Q.infinite(n) & Q.integer(n))


def test_min_max_no_rule_is_noop_without_relations() -> None:
    # A general Mul-style check that the Min/Max handlers never guess: no
    # relation means no selection, even for equal-looking expressions.
    assert refine(Min(x, y), Q.eq(x, y)) == Min(x, y)
    assert refine(Max(x, y), Q.eq(x, y)) == Max(x, y)
    assert refine(Min(x, y, z), Q.le(x, y) & Q.le(z, y)) == Min(x, y, z)
    assert refine(Max(x, y, z), Q.ge(x, y) & Q.ge(z, y)) == Max(x, y, z)


def test_scope_mul_key_is_documented_auxiliary_key() -> None:
    # ``Mul`` is outside the nominal conjugate ownership; the module docstring
    # must say so, and no other module may claim the key.
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "refine"
        / "handlers"
        / "conjugate.py"
    )
    text = path.read_text()
    assert "auxiliary" in text
    assert "handlers_dict['Mul']" in text
