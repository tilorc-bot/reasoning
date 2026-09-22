"""Refine handler for :class:`~sympy.functions.elementary.complexes.arg`.

Keeps the vendored positive/negative behavior and adds the cases from upstream
PR #29409:

* ``arg(x) -> nan`` under ``Q.zero(x)`` (the argument of zero is undefined);
* ``arg(x) -> pi/2`` (resp. ``-pi/2``) for imaginary ``x`` when the sign of
  ``im(x)`` is known.

The sign of the imaginary part is the only thing that distinguishes the two
imaginary values (``arg(i*y)`` is ``pi/2`` for ``y > 0`` and ``-pi/2`` for
``y < 0``), so without a query that answers ``Q.positive(im(x))`` or
``Q.negative(im(x))`` the expression is left unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_arg(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    refined = _upstream.refine_arg(expr, assumptions)
    if refined is not None:
        return refined

    from sympy.functions.elementary.complexes import im

    arg = expr.args[0]
    if _upstream.ask(Q.zero(arg), assumptions):
        return S.NaN
    if _upstream.ask(Q.imaginary(arg), assumptions):
        arg_im = im(arg)
        if _upstream.ask(Q.positive(arg_im), assumptions):
            return S.Pi / 2
        if _upstream.ask(Q.negative(arg_im), assumptions):
            return -S.Pi / 2
    return None


handlers_dict['arg'] = refine_arg
