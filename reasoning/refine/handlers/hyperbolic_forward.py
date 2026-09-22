"""Refine handlers for the six hyperbolic functions.

Upstream SymPy has no hyperbolic refine handler; the period rules mirror PRs
#30192 and #30138.  ``sinh``/``cosh``/``sech``/``csch`` change sign under a
shift by ``pi*I`` and repeat after ``2*pi*I``, while ``tanh``/``coth`` already
repeat after ``pi*I``.  A shift term that is a known integer multiple of
``pi*I`` is split off; the sign family additionally needs the parity of the
coefficient, so a coefficient of unknown parity stays inside the function.
``tanh`` has poles at odd multiples of ``pi*I/2`` and ``coth`` at integer
multiples of ``pi*I``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sympy.assumptions import Q
from sympy.core import Add, Basic, S

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


PI_I = S.Pi * S.ImaginaryUnit


def _pi_i_coefficient(term: Any) -> Any:
    """Return the coefficient of ``pi*I`` in ``term``, or ``None``."""
    return term.as_coefficient(PI_I)


def _is_odd_half_integer(coeff: Any, assumptions: Boolean | bool) -> bool:
    """Whether ``coeff`` is provably an integer plus ``1/2``."""
    if _upstream.ask(Q.integer(coeff - S.Half), assumptions):
        return True
    return _upstream.ask(Q.odd(2 * coeff), assumptions) is True


def refine_hyperbolic(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    """Refine a hyperbolic function under zero, period and pole rules."""
    from sympy.functions.elementary.hyperbolic import (
        cosh,
        coth,
        csch,
        sech,
        sinh,
        tanh,
    )

    arg = expr.args[0]
    if _upstream.ask(Q.zero(arg), assumptions):
        if isinstance(expr, (sinh, tanh)):
            return S.Zero
        if isinstance(expr, (cosh, sech)):
            return S.One
        return S.ComplexInfinity

    parity_known: list[tuple[Any, bool]] = []
    integer_only: list[Any] = []
    other_terms: list[Any] = []
    pure_coefficient = S.Zero
    is_pure = True

    terms = arg.args if arg.is_Add else (arg,)
    for term in terms:
        coeff = _pi_i_coefficient(term)
        if coeff is None:
            is_pure = False
            other_terms.append(term)
            continue
        pure_coefficient += coeff
        if not _upstream.ask(Q.integer(coeff), assumptions):
            other_terms.append(term)
            continue
        is_even = _upstream.ask(Q.even(coeff), assumptions)
        if is_even is None:
            integer_only.append(coeff)
        else:
            parity_known.append((coeff, is_even))

    if isinstance(expr, (sinh, cosh, sech, csch)):
        if not parity_known:
            return None
        shift_is_even = True
        for _, coeff_is_even in parity_known:
            shift_is_even = shift_is_even == coeff_is_even
        remaining = Add(*other_terms, *[coeff * PI_I for coeff in integer_only])
        if shift_is_even:
            return expr.func(remaining)
        return -expr.func(remaining)

    if parity_known or integer_only:
        return expr.func(Add(*other_terms))

    if is_pure and _is_odd_half_integer(pure_coefficient, assumptions):
        if isinstance(expr, tanh):
            return S.ComplexInfinity
        return S.Zero
    return None


handlers_dict['sinh'] = refine_hyperbolic
handlers_dict['cosh'] = refine_hyperbolic
handlers_dict['tanh'] = refine_hyperbolic
handlers_dict['coth'] = refine_hyperbolic
handlers_dict['sech'] = refine_hyperbolic
handlers_dict['csch'] = refine_hyperbolic
