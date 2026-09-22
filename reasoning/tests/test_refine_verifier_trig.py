"""Adversarial verifier tests for the trig / hyperbolic / inverse-trig handlers.

Written by the independent verifier (fresh context, no access to the
implementers' notes).  These tests supplement, not replace, the package tests
in ``test_refine_trig_*.py``, ``test_refine_hyperbolic_*.py`` and
``test_refine_inverse_trig.py``.  They focus on material the package tests do
not cover:

* boundary values ``0``, ``+-1``, ``+-pi/2``, ``+-pi``, poles, ``zoo``/``nan``
  and non-real samples;
* satisfiable assumption sets that do not imply a rule (must leave the
  expression unchanged);
* unknown parity / missing integer assumptions / negative shifts / rational
  coefficients / complex samples;
* numeric counterexample searches through the harness oracle with explicit
  ``values=`` lists;
* scripted ``ask`` sequences mixing ``None``/``True``/``False`` and
  fixed-point (termination) checks;
* reference-ask fidelity of the guarded ``sin``/``cos`` handler.

Verified findings, both fixed after the verifier report:

* ``atan(tan(x)) -> x`` was invalid at ``x = +-pi/2`` (``tan`` has a pole and
  the original is ``atan(zoo)``); the handler now requires the open interval
  (``Q.gt``/``Q.lt``).  See
  :func:`test_atan_rule_at_closed_interval_endpoints`.
* The quoted report rule ``sinh(x + n*pi*I) -> (-1)**n*sinh(x)`` under merely
  ``Q.integer(n)`` was not implemented; the handler now emits the ``(-1)**n``
  form.  See :func:`test_hyperbolic_integer_shift_is_conservative`.
"""
from __future__ import annotations

import ast
import pathlib
import re
from collections import defaultdict
from typing import Any

import pytest
from sympy import I, ask, pi
from sympy.abc import m, n, x
from sympy.assumptions import Q
from sympy.core import S
from sympy.core.numbers import zoo
from sympy.functions.elementary.hyperbolic import (
    acosh,
    acoth,
    acsch,
    asech,
    asinh,
    atanh,
    cosh,
    coth,
    csch,
    sech,
    sinh,
    tanh,
)
from sympy.functions.elementary.trigonometric import (
    acos,
    asin,
    atan,
    cos,
    cot,
    csc,
    sec,
    sin,
    sinc,
    tan,
)

import reasoning.refine
from reasoning.refine import handlers_dict, refine
from reasoning.tests.refine_harness import (
    assert_refines_like_sympy,
    assert_refinement_valid,
    scripted_ask,
    stub_ask,
    use_ask,
)


IPI = I * pi
ODD = [S.One, S.NegativeOne, S(3), S(-3), S(5)]
EVEN = [S.Zero, S(2), S(-2), S(4), S(-4)]
ALL_INT = ODD + EVEN
ODD_X = [1, -1, 3, -3, 5]
EVEN_X = [0, 2, -2, 4, -4]
COMPLEX_X = [I, -I, 1 + I, 2 - 3 * I, S.Half + I]
REAL_X = [
    S.Zero, S.One, S.NegativeOne, S.Half, S(-1) / 2,
    pi / 3, -pi / 3, pi / 2, -pi / 2, pi, -pi, 3 * pi / 2, 2 * pi,
]
ASIN_BOX = Q.real(x) & Q.ge(x, -pi / 2) & Q.le(x, pi / 2)
ACOS_BOX = Q.real(x) & Q.ge(x, 0) & Q.le(x, pi)
ATAN_OPEN = Q.real(x) & Q.gt(x, -pi / 2) & Q.lt(x, pi / 2)


# ---------------------------------------------------------------------------
# scope: registry keys and ownership
# ---------------------------------------------------------------------------

_TRIG_OWNERS = {
    "tan": "trig_tan",
    "cot": "trig_cot",
    "sec": "trig_sec_csc",
    "csc": "trig_sec_csc",
    "sinc": "trig_sinc",
    "sin": "trig_sin_cos",
    "cos": "trig_sin_cos",
}
_HYPER_OWNERS = {
    key: "hyperbolic_forward"
    for key in ("sinh", "cosh", "tanh", "coth", "sech", "csch")
}
_INV_HYPER_OWNERS = {
    key: "hyperbolic_inverse"
    for key in ("asinh", "acosh", "atanh", "acoth", "asech", "acsch")
}
_INV_TRIG_OWNERS = {key: "inverse_trig" for key in ("asin", "acos", "atan")}


def test_scope_keys_owned_by_expected_modules() -> None:
    for key, module in {
        **_TRIG_OWNERS,
        **_HYPER_OWNERS,
        **_INV_HYPER_OWNERS,
        **_INV_TRIG_OWNERS,
    }.items():
        handler = handlers_dict[key]
        assert handler.__module__ == f"reasoning.refine.handlers.{module}", (
            f"key {key!r} registered by {handler.__module__}"
        )


def test_scope_no_duplicate_handler_registrations() -> None:
    root = pathlib.Path(reasoning.refine.__file__).parent / "handlers"
    key_to_files: dict[str, list[str]] = defaultdict(list)
    for path in sorted(root.glob("*.py")):
        text = path.read_text()
        for key in re.findall(r"handlers_dict\[['\"]([^'\"]+)['\"]\]", text):
            key_to_files[key].append(path.name)
    duplicates = {k: v for k, v in key_to_files.items() if len(v) > 1}
    assert not duplicates, f"duplicate handler keys: {duplicates}"
    # the shared parser must not register anything
    parser = (root / "_trig.py").read_text()
    assert "handlers_dict[" not in parser
    # AST-level check that the regex did not miss annotated assignments
    parsed = ast.parse((root / "trig_tan.py").read_text())
    assert any(
        isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Subscript)
        for node in ast.walk(parsed)
    )


def test_nonzero_is_real_in_new_assumptions() -> None:
    # The acsch/acoth/asinh rules rely on nonzero implying real; Q.nonzero is
    # Equivalent(Q.negative | Q.positive), so complex "nonzero" values such as
    # 2*I do not satisfy it.
    assert ask(Q.nonzero(x) >> Q.real(x)) is True
    assert ask(Q.nonzero(2 * I)) is False


# ---------------------------------------------------------------------------
# boundary values and poles
# ---------------------------------------------------------------------------


def test_concrete_trig_boundaries() -> None:
    assert refine(tan(pi / 2, evaluate=False), True) is zoo
    assert refine(tan(-pi / 2, evaluate=False), True) is zoo
    assert refine(tan(pi, evaluate=False), True) == 0
    assert refine(tan(-pi, evaluate=False), True) == 0
    assert refine(cot(pi / 2, evaluate=False), True) == 0
    assert refine(cot(pi, evaluate=False), True) is zoo
    assert refine(sec(pi / 2, evaluate=False), True) is zoo
    assert refine(sec(pi, evaluate=False), True) == -1
    assert refine(csc(pi, evaluate=False), True) is zoo
    assert refine(csc(pi / 2, evaluate=False), True) == 1
    assert refine(sinc(S.Zero, evaluate=False), True) == 1


def test_concrete_hyperbolic_boundaries() -> None:
    assert refine(sinh(I * pi, evaluate=False), True) == 0
    assert refine(cosh(I * pi, evaluate=False), True) == -1
    assert refine(tanh(I * pi, evaluate=False), True) == 0
    assert refine(tanh(I * pi / 2, evaluate=False), True) is zoo
    assert refine(coth(I * pi, evaluate=False), True) is zoo
    assert refine(coth(I * pi / 2, evaluate=False), True) == 0


def test_tan_cot_boundary_oracle() -> None:
    assert_refinement_valid(
        tan(x + n * pi / 2), Q.odd(n), refine(tan(x + n * pi / 2), Q.odd(n)),
        values={n: ODD, x: [S.Zero, pi / 2, pi, -pi / 2, 3 * pi / 2, I]},
    )
    assert_refinement_valid(
        cot(x + n * pi / 2), Q.odd(n), refine(cot(x + n * pi / 2), Q.odd(n)),
        values={n: ODD, x: [S.Zero, pi / 2, pi, -pi / 2, 3 * pi / 2, I]},
    )


def test_sec_csc_boundary_oracle() -> None:
    for expr, A, values in (
        (sec(n * pi), Q.integer(n), {n: ALL_INT}),
        (sec(n * pi / 2), Q.odd(n), {n: ODD}),
        (sec(n * pi / 2), Q.even(n), {n: EVEN}),
        (csc(n * pi), Q.integer(n), {n: ALL_INT}),
        (csc(n * pi / 2), Q.odd(n), {n: ODD}),
        (csc(n * pi / 2), Q.even(n), {n: EVEN}),
    ):
        assert_refinement_valid(expr, A, refine(expr, A), values=values)


def test_hyperbolic_forward_boundary_oracle() -> None:
    for expr, A, values in (
        (sinh(x + n * IPI), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (cosh(x + n * IPI), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (sech(x + n * IPI), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (csch(x + n * IPI), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (tanh(x + n * IPI), Q.integer(n), {n: ALL_INT, x: COMPLEX_X}),
        (coth(x + n * IPI), Q.integer(n), {n: ALL_INT, x: COMPLEX_X}),
        (tanh(n * IPI / 2), Q.odd(n), {n: ODD}),
        (coth(n * IPI / 2), Q.odd(n), {n: ODD}),
        (coth(n * IPI), Q.integer(n), {n: ALL_INT}),
    ):
        assert_refinement_valid(expr, A, refine(expr, A), values=values)


def test_trig_period_rules_on_complex_samples() -> None:
    for expr, A in (
        (tan(x + n * pi / 2), Q.odd(n)),
        (cot(x + n * pi / 2), Q.odd(n)),
        (sec(x + n * pi / 2), Q.odd(n)),
        (csc(x + n * pi / 2), Q.odd(n)),
        (sin(x + n * pi / 2), Q.odd(n)),
        (cos(x + n * pi / 2), Q.odd(n)),
    ):
        assert_refinement_valid(
            expr, A, refine(expr, A), values={n: ODD, x: COMPLEX_X}
        )


# ---------------------------------------------------------------------------
# inverse functions: ranges, boundaries and the atan endpoint finding
# ---------------------------------------------------------------------------


def test_inverse_hyperbolic_boundary_oracle() -> None:
    for expr, A, values in (
        (asinh(sinh(x)), Q.real(x), {x: REAL_X}),
        (acosh(cosh(x)), Q.nonnegative(x), {x: [0, 1, S.Half, pi / 2, 2, 3]}),
        (atanh(tanh(x)), Q.real(x), {x: REAL_X}),
        (acoth(coth(x)), Q.real(x) & Q.nonzero(x),
         {x: [1, -1, S.Half, -S.Half, pi / 2, 2, 3]}),
        (asech(sech(x)), Q.nonnegative(x),
         {x: [0, 1, S.Half, pi / 2, 2, 3]}),
        (acsch(csch(x)), Q.real(x) & Q.nonzero(x),
         {x: [1, -1, S.Half, -S.Half, 2, 3]}),
    ):
        assert_refinement_valid(expr, A, refine(expr, A), values=values)


def test_inverse_trig_interior_oracle() -> None:
    assert_refinement_valid(
        asin(sin(x)), ASIN_BOX, refine(asin(sin(x)), ASIN_BOX),
        values={x: [S.Zero, S.One, S.NegativeOne, S.Half, -S.Half, pi / 2,
                    -pi / 2, pi / 3]},
    )
    assert_refinement_valid(
        acos(cos(x)), ACOS_BOX, refine(acos(cos(x)), ACOS_BOX),
        values={x: [S.Zero, S.One, S.Half, pi / 2, pi, 2, 3]},
    )
    assert_refinement_valid(
        atan(tan(x)), ATAN_OPEN, refine(atan(tan(x)), ATAN_OPEN),
        values={x: [S.Zero, S.One, S.NegativeOne, S.Half, -S.Half, 2, 3]},
    )


def test_atan_rule_at_closed_interval_endpoints() -> None:
    """The closed interval is no longer accepted for ``atan``.

    ``tan`` has a pole at ``+-pi/2``: ``atan(tan(pi/2))`` is ``atan(zoo)``
    while the old refinement returned ``pi/2``.  The handler now requires
    strict bounds, so the closed rectangle leaves the expression unchanged
    and the open interval still refines.
    """
    assert refine(atan(tan(x)), ASIN_BOX) == atan(tan(x))
    assert atan(tan(x)).subs(x, pi / 2) != pi / 2
    assert refine(atan(tan(x)), ATAN_OPEN) == x


# ---------------------------------------------------------------------------
# satisfiable assumptions that do not imply the rule -> unchanged
# ---------------------------------------------------------------------------


def test_non_implying_assumptions_leave_expression_unchanged() -> None:
    cases: list[tuple[Any, Any]] = [
        (tan(x), Q.positive(x)),
        (tan(n * pi), Q.real(n)),
        (tan(n * pi / 2), Q.integer(n)),
        (tan(x + n * pi), Q.real(n)),
        (tan(x + n * pi / 2), Q.integer(n)),
        (cot(x), Q.nonzero(x)),
        (cot(n * pi / 2), Q.integer(n)),
        (cot(x + n * pi), Q.real(n)),
        (sec(n * pi), Q.positive(n)),
        (sec(n * pi / 2), Q.integer(n)),
        (sec(x + n * pi / 2), Q.integer(n)),
        (csc(n * pi), Q.real(n)),
        (csc(n * pi / 2), Q.integer(n)),
        (sinc(x), Q.nonzero(x)),
        (sinc(x), Q.real(x)),
        (sinh(x + n * IPI), Q.real(n)),
        (cosh(x + n * IPI), Q.real(n)),
        (tanh(n * IPI / 2), Q.integer(n)),
        (asinh(sinh(x)), Q.imaginary(x)),
        (acosh(cosh(x)), Q.real(x)),
        (atanh(tanh(x)), Q.imaginary(x)),
        (acoth(coth(x)), Q.real(x)),
        (asech(sech(x)), Q.real(x)),
        (acsch(csch(x)), Q.imaginary(x)),
        (asin(sin(x)), Q.real(x)),
        (acos(cos(x)), Q.real(x)),
        (atan(tan(x)), Q.real(x)),
        (asin(sin(x)), Q.real(x) & Q.ge(x, pi / 2) & Q.le(x, 3 * pi / 2)),
        (acos(cos(x)), Q.real(x) & Q.ge(x, -pi) & Q.le(x, 0)),
        (atan(tan(x)), Q.real(x) & Q.ge(x, pi / 2) & Q.le(x, 3 * pi / 2)),
    ]
    for expr, assumptions in cases:
        assert refine(expr, assumptions) == expr, (expr, assumptions)


def test_unknown_parity_and_missing_integer_assumption() -> None:
    assert refine(tan(n * pi / 2), Q.integer(n)) == tan(n * pi / 2)
    assert refine(cot(n * pi / 2), Q.integer(n)) == cot(n * pi / 2)
    assert refine(sec(n * pi / 2), Q.integer(n)) == sec(n * pi / 2)
    assert refine(csc(n * pi / 2), Q.integer(n)) == csc(n * pi / 2)
    # `n` without any integer assumption: 2*n*pi/2 = n*pi is not a known shift
    assert refine(tan(x + n * pi), True) == tan(x + n * pi)
    assert refine(sinh(x + 2 * n * IPI), True) == sinh(x + 2 * n * IPI)


# ---------------------------------------------------------------------------
# negative shifts and rational coefficients
# ---------------------------------------------------------------------------


def test_negative_shifts_and_rational_coefficients() -> None:
    assert refine(tan(x - pi), True) == tan(x)
    assert refine(tan(x - pi / 2), True) == -cot(x)
    assert refine(cot(x - pi / 2), True) == -tan(x)
    assert refine(sec(x - pi), True) == -sec(x)
    assert refine(csc(x - pi / 2), True) == -sec(x)
    assert refine(sec(x + S(3) * pi / 2), True) == csc(x)
    assert refine(csc(x - S(3) * pi / 2), True) == sec(x)
    assert refine(sinh(x - n * IPI), Q.odd(n)) == -sinh(x)
    assert refine(cosh(x - n * IPI), Q.odd(n)) == -cosh(x)
    for expr, A, values in (
        (tan(x - n * pi / 2), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (cot(x - n * pi / 2), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (sec(x - n * pi / 2), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (csc(x - n * pi / 2), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (sinh(x - n * IPI), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (cosh(x - n * IPI), Q.odd(n), {n: ODD, x: COMPLEX_X}),
        (sec(x + m * pi / 2), Q.even(m), {m: EVEN, x: COMPLEX_X}),
        (csc(x + m * pi / 2), Q.even(m), {m: EVEN, x: COMPLEX_X}),
    ):
        assert_refinement_valid(expr, A, refine(expr, A), values=values)


def test_mixed_known_and_unknown_parity_shifts() -> None:
    # n is a known even shift, m keeps unknown parity: m stays in the argument
    A = Q.integer(n) & Q.integer(m)
    assert refine(tan(x + n * pi + m * pi / 2), A) == tan(x + m * pi / 2)
    assert refine(sec(x + n * pi + m * pi / 2), A) == \
        (-1) ** n * sec(x + m * pi / 2)
    assert refine(csc(x + n * pi + m * pi / 2), A) == \
        (-1) ** n * csc(x + m * pi / 2)
    assert_refinement_valid(
        tan(x + n * pi + m * pi / 2), A,
        refine(tan(x + n * pi + m * pi / 2), A),
        values={n: ALL_INT, m: ALL_INT, x: COMPLEX_X},
    )
    assert_refinement_valid(
        sinh(x + n * IPI + m * IPI), Q.odd(n) & Q.even(m),
        refine(sinh(x + n * IPI + m * IPI), Q.odd(n) & Q.even(m)),
        values={n: ODD, m: EVEN, x: COMPLEX_X},
    )


# ---------------------------------------------------------------------------
# fidelity: quoted outputs and reference ask
# ---------------------------------------------------------------------------


def test_quoted_rule_outputs() -> None:
    assert refine(tan(x), Q.zero(x)) == 0
    assert refine(tan(n * pi), Q.integer(n)) == 0
    assert refine(tan(x + n * pi), Q.integer(n)) == tan(x)
    assert refine(tan(n * pi / 2), Q.odd(n)) is zoo
    assert refine(tan(x + n * pi / 2), Q.odd(n)) == -cot(x)
    assert refine(cot(x), Q.zero(x)) is zoo
    assert refine(cot(n * pi / 2), Q.odd(n)) == 0
    assert refine(cot(x + n * pi), Q.integer(n)) == cot(x)
    assert refine(cot(x + n * pi / 2), Q.odd(n)) == -tan(x)
    assert refine(sec(n * pi), Q.integer(n)) == (-1) ** n
    assert refine(sec(x + n * pi / 2), Q.odd(n)) == \
        (-1) ** ((n + 1) / 2) * csc(x)
    assert refine(sec(n * pi / 2), Q.odd(n)) is zoo
    assert refine(csc(n * pi), Q.integer(n)) is zoo
    assert refine(csc(n * pi / 2), Q.odd(n) & Q.even((n - 1) / 2)) == 1
    assert refine(csc(n * pi / 2), Q.odd(n) & Q.odd((n - 1) / 2)) == -1
    assert refine(csc(x + n * pi / 2), Q.odd(n)) == \
        (-1) ** ((n + 3) / 2) * sec(x)
    assert refine(sinc(x), Q.zero(x)) == 1
    assert refine(sinh(x), Q.zero(x)) == 0
    assert refine(cosh(x), Q.zero(x)) == 1
    assert refine(tanh(x), Q.zero(x)) == 0
    assert refine(coth(x), Q.zero(x)) is zoo
    assert refine(sech(x), Q.zero(x)) == 1
    assert refine(csch(x), Q.zero(x)) is zoo
    assert refine(tanh(x + n * IPI), Q.integer(n)) == tanh(x)
    assert refine(coth(x + n * IPI), Q.integer(n)) == coth(x)
    assert refine(asinh(sinh(x)), Q.real(x)) == x
    assert refine(acosh(cosh(x)), Q.nonnegative(x)) == x
    assert refine(atanh(tanh(x)), Q.real(x)) == x
    assert refine(acoth(coth(x)), Q.real(x) & Q.nonzero(x)) == x
    assert refine(asech(sech(x)), Q.nonnegative(x)) == x
    assert refine(acsch(csch(x)), Q.real(x) & Q.nonzero(x)) == x
    assert refine(asin(sin(x)), ASIN_BOX) == x
    assert refine(acos(cos(x)), ACOS_BOX) == x
    assert refine(atan(tan(x)), ATAN_OPEN) == x


def test_hyperbolic_integer_shift_is_conservative() -> None:
    """The quoted ``(-1)**n`` rule is now implemented.

    The report rule is ``sinh(x + n*pi*I) -> (-1)**n*sinh(x)`` for
    ``Q.integer(n)``; the handler emits the symbolic sign factor when the
    parity is unknown and reduces it when it is known.
    """
    for func in (sinh, cosh, sech, csch):
        assert refine(func(x + n * IPI), Q.integer(n)) == (-1) ** n * func(x)
        assert refine(func(x + 2 * n * IPI), Q.integer(n)) == func(x)
        assert refine(func(x + (2 * n + 1) * IPI), Q.integer(n)) == -func(x)
    assert refine(tanh(x + n * IPI), Q.integer(n)) == tanh(x)
    # the analogous trig handler does emit the (-1)**n form
    assert refine(sin(x + n * pi), Q.integer(n)) == (-1) ** n * sin(x)


def test_sin_cos_matches_sympy_under_reference_ask() -> None:
    corpus = [
        (sin(x), True),
        (cos(x), Q.zero(x)),
        (sin(n * pi), Q.integer(n)),
        (cos(n * pi), Q.even(n)),
        (cos(n * pi), Q.odd(n)),
        (sin(n * pi / 2), Q.even(n)),
        (cos(n * pi / 2), Q.odd(n)),
        (sin(n * pi / 2), Q.odd(n) & Q.even((n - 1) / 2)),
        (sin(x + n * pi / 2), Q.odd(n)),
        (cos(x + n * pi / 2), Q.integer(n)),
        (cos(x + n * pi / 2), Q.even(n)),
        (sin(x), Q.infinite(x) & Q.extended_real(x)),
        (cos(x), Q.infinite(x) & Q.extended_real(x)),
        (sin(pi + x, evaluate=False), True),
        (cos(pi + x, evaluate=False), True),
        (sin(pi / 2 + x, evaluate=False), True),
        (sin(2 * pi + x, evaluate=False), True),
    ]
    for expr, assumptions in corpus:
        assert_refines_like_sympy(expr, assumptions)


# ---------------------------------------------------------------------------
# robustness: scripted ask, no NaN/pole crashes, fixed points
# ---------------------------------------------------------------------------


NONE_SAFE_CASES: list[tuple[Any, Any]] = [
    (tan(x), Q.zero(x)),
    (tan(n * pi), Q.integer(n)),
    (tan(x + n * pi / 2), Q.odd(n)),
    (cot(x), Q.zero(x)),
    (cot(n * pi / 2), Q.odd(n)),
    (sec(x), Q.zero(x)),
    (sec(n * pi), Q.integer(n)),
    (sec(x + n * pi / 2), Q.odd(n)),
    (csc(n * pi), Q.integer(n)),
    (csc(x + n * pi / 2), Q.odd(n)),
    (sinc(x), Q.zero(x)),
    (sinh(x), Q.zero(x)),
    (sinh(x + n * IPI), Q.odd(n)),
    (cosh(x + n * IPI), Q.even(n)),
    (tanh(x + n * IPI), Q.integer(n)),
    (coth(x), Q.zero(x)),
    (sech(x + n * IPI), Q.odd(n)),
    (csch(x), Q.zero(x)),
    (tanh(n * IPI / 2), Q.odd(n)),
    (coth(n * IPI), Q.integer(n)),
    (asinh(sinh(x)), Q.real(x)),
    (acosh(cosh(x)), Q.nonnegative(x)),
    (atanh(tanh(x)), Q.real(x)),
    (acoth(coth(x)), Q.real(x) & Q.nonzero(x)),
    (asech(sech(x)), Q.nonnegative(x)),
    (acsch(csch(x)), Q.nonzero(x)),
    (asin(sin(x)), Q.real(x)),
    (acos(cos(x)), Q.real(x)),
    (atan(tan(x)), Q.real(x)),
]


def test_none_answers_leave_expression_unchanged() -> None:
    with use_ask(stub_ask({})):
        for expr, assumptions in NONE_SAFE_CASES:
            assert refine(expr, assumptions) == expr, (expr, assumptions)


def test_scripted_mixed_answers_do_not_raise() -> None:
    scripts: list[list[bool | None]] = [
        [None] * 10,
        [True, False, None, True, None, False, None, True],
        [False, True, None, False, True, None, False],
        [True] * 8,
        [False] * 8,
        [None, True, None, False] * 3,
    ]
    for script in scripts:
        for expr, assumptions in NONE_SAFE_CASES:
            fake_ask, _ = scripted_ask(script)
            with use_ask(fake_ask):
                refine(expr, assumptions)


def test_poles_and_special_values_do_not_raise() -> None:
    values = [zoo, S.ComplexInfinity, S.NaN, S.Infinity, S.NegativeInfinity]
    for value in values:
        for func in (tan, cot, sec, csc, sinc, tanh, coth, asech, acsch):
            expr = func(value, evaluate=False)
            refine(expr, True)
            refine(expr, Q.zero(x))


FIXED_POINT_CASES: list[tuple[Any, Any]] = [
    (tan(x), Q.zero(x)),
    (tan(x + n * pi), Q.integer(n)),
    (tan(x + n * pi / 2), Q.odd(n)),
    (cot(x), Q.zero(x)),
    (cot(x + n * pi / 2), Q.odd(n)),
    (sec(n * pi), Q.integer(n)),
    (sec(x + n * pi / 2), Q.odd(n)),
    (csc(n * pi), Q.integer(n)),
    (csc(x + n * pi / 2), Q.odd(n)),
    (sinc(x), Q.zero(x)),
    (sinh(x + n * IPI), Q.odd(n)),
    (cosh(x + n * IPI), Q.even(n)),
    (tanh(x + n * IPI), Q.integer(n)),
    (coth(x + n * IPI), Q.integer(n)),
    (tanh(n * IPI / 2), Q.odd(n)),
    (coth(n * IPI), Q.integer(n)),
    (asinh(sinh(x)), Q.real(x)),
    (acosh(cosh(x)), Q.nonnegative(x)),
    (atanh(tanh(x)), Q.real(x)),
    (acoth(coth(x)), Q.real(x) & Q.nonzero(x)),
    (asech(sech(x)), Q.nonnegative(x)),
    (acsch(csch(x)), Q.nonzero(x)),
    (asin(sin(x)), ASIN_BOX),
    (acos(cos(x)), ACOS_BOX),
    (atan(tan(x)), ASIN_BOX),
]


def test_handlers_reach_a_fixed_point() -> None:
    for expr, assumptions in FIXED_POINT_CASES:
        once = refine(expr, assumptions)
        assert refine(once, assumptions) == once, (expr, assumptions)
