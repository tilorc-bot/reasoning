"""Guarded copy of the vendored ``refine_sin_cos`` handler.

The vendored :func:`reasoning.refine._upstream.refine_sin_cos` has a latent
``AttributeError`` (PR #29450): ``pow_expr = (-1)**(k/2)`` can evaluate to an
``Integer`` (e.g. ``1`` or ``-1``) before reaching ``refine_Pow``, which then
crashes accessing ``.base``.  ``_upstream`` must stay behavior-identical to
upstream, so this module copies the body and only calls ``refine_Pow`` when
the factor actually is a :class:`~sympy.core.power.Pow`; everything else,
including the ``TypeError`` for non-``sin``/``cos`` inputs, is unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic, Pow

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_sin_cos(expr: Basic, assumptions: Boolean | bool) -> Basic | int:
    """
    Handler for sin and cos functions.

    Examples
    ========

    >>> from sympy.assumptions.refine import refine_sin_cos
    >>> from sympy import Symbol, Q, sin, cos, pi
    >>> from sympy.abc import x, y
    >>> n = Symbol('n')
    >>> refine_sin_cos(cos(n*pi), Q.even(n))
    1
    >>> refine_sin_cos(sin(n*pi/2), Q.odd(n) & Q.odd((n-1)/2))
    -1
    >>> refine_sin_cos(sin(x + n*pi/2), Q.odd(n))
    (-1)**(n/2 + 3/2)*cos(x)
    >>> refine_sin_cos(cos(x + n*pi/2), Q.even(n))
    (-1)**(n/2)*cos(x)
    >>> refine_sin_cos(cos(x + y + 2*n*pi), Q.integer(n))
    cos(x + y)
    """
    from sympy.functions.elementary.trigonometric import sin, cos
    from sympy.calculus.accumulationbounds import AccumBounds

    if not isinstance(expr, (sin, cos)):
        raise TypeError("refine_sin_cos expects a sin or cos function.")

    arg = expr.args[0]
    expr_is_sin = isinstance(expr, sin)

    if (_upstream.ask(Q.infinite(arg), assumptions) and
            _upstream.ask(Q.extended_real(arg), assumptions)):
        return AccumBounds(-1, 1)

    if _upstream.ask(Q.zero(arg), assumptions):
        return 0 if expr_is_sin else 1

    integer_coeffs_of_pi_half = []
    remaining_terms = []

    terms = arg.args if arg.is_Add else (arg,)
    for term in terms:
        coeff_of_pi = term.coeff(S.Pi)
        if coeff_of_pi and _upstream.ask(Q.integer(2 * coeff_of_pi),
                                         assumptions):
            coeff_of_pi_half = 2 * coeff_of_pi
            integer_coeffs_of_pi_half.append(coeff_of_pi_half)
        else:
            remaining_terms.append(term)

    if not integer_coeffs_of_pi_half:
        return expr

    sum_of_parity_known_coeffs = 0
    sum_of_parity_unknown_coeffs = 0
    sum_of_parity_known_coeffs_is_even = True
    for coeff in integer_coeffs_of_pi_half:
        coeff_is_even = _upstream.ask(Q.even(coeff), assumptions)
        if coeff_is_even is None:
            sum_of_parity_unknown_coeffs += coeff
        else:
            sum_of_parity_known_coeffs += coeff
            sum_of_parity_known_coeffs_is_even = (
                sum_of_parity_known_coeffs_is_even == coeff_is_even
            )

    if sum_of_parity_known_coeffs == 0:
        return expr

    # Treat sin as a phase-shifted cosine so a single logic path can handle both.
    if expr_is_sin:
        k = sum_of_parity_known_coeffs - 1
        k_is_even = not sum_of_parity_known_coeffs_is_even
    else:
        k = sum_of_parity_known_coeffs
        k_is_even = sum_of_parity_known_coeffs_is_even

    # If k is even:
    #    `cos(rem + k*pi/2)` -> `(-1)^(k/2) * cos(rem)`
    #
    # If k is odd:
    #    `cos(rem + k*pi/2)` -> `(-1)^((k+1)/2) * sin(rem)`
    rem = sum(remaining_terms) + sum_of_parity_unknown_coeffs * S.Pi / 2
    if k_is_even:
        pow_expr = (-1)**(k / 2)
        if isinstance(pow_expr, Pow):
            refined_pow = _upstream.refine_Pow(pow_expr, assumptions)
            pow_expr = pow_expr if refined_pow is None else refined_pow
        return pow_expr * cos(rem)
    else:
        pow_expr = (-1)**((k + 1) / 2)
        if isinstance(pow_expr, Pow):
            refined_pow = _upstream.refine_Pow(pow_expr, assumptions)
            pow_expr = pow_expr if refined_pow is None else refined_pow
        return pow_expr * sin(rem)


handlers_dict['sin'] = refine_sin_cos
handlers_dict['cos'] = refine_sin_cos
