"""Refine handler for ``sec`` and ``csc``.

Upstream SymPy has no ``sec``/``csc`` handler; the rules mirror PRs #29948 and
#29942 and reuse the shared ``pi/2`` parser of :mod:`._trig`.

Writing ``sec = 1/cos`` and ``csc = 1/sin``, the reciprocal of
``cos(rem + k*pi/2)`` or ``sin(rem + k*pi/2)`` is a power of ``-1`` times
``sec(rem)``/``csc(rem)`` (even ``k``) or the other reciprocal function (odd
``k``).  A vanishing reciprocal means the original function has a pole.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sympy.assumptions import Q
from sympy.core import S, Basic, Pow

from .. import _upstream
from .._upstream import handlers_dict
from ._trig import remainder, split_pi_half

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def _minus_one_power(exponent: Any, assumptions: Boolean | bool) -> Any:
    """Build ``(-1)**exponent``, refining it only when it is a genuine power.

    ``(-1)**exponent`` can evaluate to an ``Integer`` before reaching
    :func:`refine_Pow` (the latent bug fixed by PR #29450), and
    ``refine_Pow`` crashes on non-``Pow`` inputs by accessing ``.base``.
    """
    factor = (-1)**exponent
    if isinstance(factor, Pow):
        refined = _upstream.refine_Pow(factor, assumptions)
        if refined is not None:
            return refined
    return factor


def refine_sec_csc(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.trigonometric import cos, csc, sec, sin

    arg = expr.args[0]
    is_sec = isinstance(expr, sec)
    if _upstream.ask(Q.zero(arg), assumptions):
        return S.One if is_sec else S.ComplexInfinity

    split = split_pi_half(arg, assumptions)
    if split is None:
        return expr

    rem = remainder(split)
    k = split.known_sum
    if split.known_sum_is_even:
        factor = _minus_one_power(k / 2, assumptions)
        zero_value = cos(rem) if is_sec else sin(rem)
        value_func = sec if is_sec else csc
    elif is_sec:
        factor = _minus_one_power((k + 1) / 2, assumptions)
        zero_value = sin(rem)
        value_func = csc
    else:
        # (k - 1)/2 differs from (k + 3)/2 by two, so the power of -1 is the
        # same while refine_Pow can reduce it using the parity of (k - 1)/2.
        factor = _minus_one_power((k - 1) / 2, assumptions)
        zero_value = cos(rem)
        value_func = sec

    if zero_value == 0:
        return S.ComplexInfinity
    return factor * value_func(rem)


handlers_dict['sec'] = refine_sec_csc
handlers_dict['csc'] = refine_sec_csc
