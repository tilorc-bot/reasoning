"""Refine handler for :class:`~sympy.functions.elementary.miscellaneous.Max`.

Rules (missing-handler report section 3.9, refs #29406/#30487):

* ``Max(x, y)`` under ``Q.ge(x, y)`` is ``x``; under ``Q.le(x, y)`` is ``y``
  (each direction is asked in both operand orders, because the engine does not
  reverse an ``le``/``ge`` relation by itself).
* ``Max(x, 0)`` under ``Q.positive(x)`` is ``x``; under ``Q.zero(x)`` is ``0``
  (``x >= 0`` follows from ``Q.nonnegative(x)``, which is asked for the zero
  argument).
* A multi-argument ``Max`` reduces to one argument only when that argument is
  provably greater than or equal to every other argument.
* A provably positive-infinite argument is the maximum; provably
  negative-infinite arguments are dropped, so an all-negative-infinite ``Max``
  is ``-oo``.  Literal infinities already evaluate at construction.

No rule is applied when the corresponding query answers ``None``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def _le(a: Basic, b: Basic, assumptions: Boolean | bool) -> bool:
    """Return ``True`` only when ``a <= b`` is implied by ``assumptions``."""
    if _upstream.ask(Q.le(a, b), assumptions) is True:
        return True
    if _upstream.ask(Q.lt(a, b), assumptions) is True:
        return True
    if _upstream.ask(Q.ge(b, a), assumptions) is True:
        return True
    if _upstream.ask(Q.gt(b, a), assumptions) is True:
        return True
    if a is S.Zero and _upstream.ask(Q.nonnegative(b), assumptions) is True:
        return True
    if b is S.Zero and _upstream.ask(Q.nonpositive(a), assumptions) is True:
        return True
    return False


def refine_Max(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    args = expr.args
    for index, candidate in enumerate(args):
        if all(
            _le(other, candidate, assumptions)
            for other_index, other in enumerate(args)
            if other_index != index
        ):
            return candidate

    for arg in args:
        if _upstream.ask(Q.positive_infinite(arg), assumptions) is True:
            return arg

    finite_args = [
        arg for arg in args
        if _upstream.ask(Q.negative_infinite(arg), assumptions) is not True
    ]
    if len(finite_args) != len(args):
        if not finite_args:
            return S.NegativeInfinity
        return expr.func(*finite_args)

    return None


handlers_dict['Max'] = refine_Max
