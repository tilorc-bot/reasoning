"""Refine handlers for the six inverse hyperbolic functions.

Upstream SymPy has no inverse hyperbolic handler.  Each function is the exact
inverse of its hyperbolic counterpart on a domain that is described by a
single assumption:

* ``asinh(sinh(x)) -> x`` for real ``x``
* ``acosh(cosh(x)) -> x`` for nonnegative real ``x`` (``-x`` otherwise)
* ``atanh(tanh(x)) -> x`` for real ``x``
* ``acoth(coth(x)) -> x`` for real nonzero ``x``
* ``asech(sech(x)) -> x`` for nonnegative real ``x``
* ``acsch(csch(x)) -> x`` for real nonzero ``x``

Nothing is refined when the corresponding predicate is not provable.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_asinh(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.hyperbolic import sinh

    arg = expr.args[0]
    if isinstance(arg, sinh):
        inner = arg.args[0]
        if _upstream.ask(Q.real(inner), assumptions):
            return inner
    return None


def refine_acosh(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.hyperbolic import cosh

    arg = expr.args[0]
    if isinstance(arg, cosh):
        inner = arg.args[0]
        if _upstream.ask(Q.nonnegative(inner), assumptions):
            return inner
    return None


def refine_atanh(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.hyperbolic import tanh

    arg = expr.args[0]
    if isinstance(arg, tanh):
        inner = arg.args[0]
        if _upstream.ask(Q.real(inner), assumptions):
            return inner
    return None


def refine_acoth(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.hyperbolic import coth

    arg = expr.args[0]
    if isinstance(arg, coth):
        inner = arg.args[0]
        if (_upstream.ask(Q.real(inner), assumptions)
                and _upstream.ask(Q.nonzero(inner), assumptions)):
            return inner
    return None


def refine_asech(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.hyperbolic import sech

    arg = expr.args[0]
    if isinstance(arg, sech):
        inner = arg.args[0]
        if _upstream.ask(Q.nonnegative(inner), assumptions):
            return inner
    return None


def refine_acsch(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.hyperbolic import csch

    arg = expr.args[0]
    if isinstance(arg, csch):
        inner = arg.args[0]
        if _upstream.ask(Q.nonzero(inner), assumptions):
            return inner
    return None


handlers_dict['asinh'] = refine_asinh
handlers_dict['acosh'] = refine_acosh
handlers_dict['atanh'] = refine_atanh
handlers_dict['acoth'] = refine_acoth
handlers_dict['asech'] = refine_asech
handlers_dict['acsch'] = refine_acsch
