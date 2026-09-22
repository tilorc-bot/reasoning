"""Refine handlers for ``asin``, ``acos`` and ``atan``.

Upstream SymPy has no inverse trigonometric handler.  The rules cancel the
inner trigonometric function only on the principal branch of the inverse,
which is a closed rectangle in the real line:

* ``asin(sin(x)) -> x`` for real ``x`` in ``[-pi/2, pi/2]``
* ``acos(cos(x)) -> x`` for real ``x`` in ``[0, pi]``
* ``atan(tan(x)) -> x`` for real ``x`` in the open interval
  ``(-pi/2, pi/2)`` (``tan`` has poles at the closed-interval endpoints)

Nothing is refined when any of the range predicates is not provable.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Basic, S

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_asin(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.trigonometric import sin

    arg = expr.args[0]
    if isinstance(arg, sin):
        inner = arg.args[0]
        if (_upstream.ask(Q.real(inner), assumptions)
                and _upstream.ask(Q.ge(inner, -S.Pi / 2), assumptions)
                and _upstream.ask(Q.le(inner, S.Pi / 2), assumptions)):
            return inner
    return None


def refine_acos(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.trigonometric import cos

    arg = expr.args[0]
    if isinstance(arg, cos):
        inner = arg.args[0]
        if (_upstream.ask(Q.real(inner), assumptions)
                and _upstream.ask(Q.ge(inner, 0), assumptions)
                and _upstream.ask(Q.le(inner, S.Pi), assumptions)):
            return inner
    return None


def refine_atan(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.trigonometric import tan

    arg = expr.args[0]
    if isinstance(arg, tan):
        inner = arg.args[0]
        if (_upstream.ask(Q.real(inner), assumptions)
                and _upstream.ask(Q.gt(inner, -S.Pi / 2), assumptions)
                and _upstream.ask(Q.lt(inner, S.Pi / 2), assumptions)):
            return inner
    return None


handlers_dict['asin'] = refine_asin
handlers_dict['acos'] = refine_acos
handlers_dict['atan'] = refine_atan
