"""Refine handler for :class:`~sympy.functions.combinatorial.factorials.factorial`.

Rules (missing-handler report section 3.6, ref #29203):

* ``factorial(n)`` under ``Q.zero(n)`` is ``1`` (``0! = 1``).
* ``factorial(n)`` under ``Q.eq(n, 1)`` is ``1``.
* ``factorial(n)`` under ``Q.integer(n) & Q.negative(n)`` is ``zoo``: ``gamma``
  has a pole at every nonpositive integer.
* ``factorial(n)`` under ``Q.positive_infinite(n)`` is ``oo``.
* ``factorial(n)`` under ``Q.negative_infinite(n)`` is ``gamma(-oo)``, the
  value of the ``factorial(n) = gamma(n + 1)`` rewrite at the pole.  ``gamma``
  has no limit at ``-oo`` (the poles at the negative integers accumulate), so
  there is no plain constant to return; this mirrors draft PR #29203.

No rule is applied when the corresponding query answers ``None``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic
from sympy.functions.special.gamma_functions import gamma

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_factorial(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    arg = expr.args[0]
    if _upstream.ask(Q.zero(arg), assumptions):
        return S.One
    if _upstream.ask(Q.eq(arg, 1), assumptions):
        return S.One
    if _upstream.ask(Q.integer(arg) & Q.negative(arg), assumptions):
        return S.ComplexInfinity
    if _upstream.ask(Q.positive_infinite(arg), assumptions):
        return S.Infinity
    if _upstream.ask(Q.negative_infinite(arg), assumptions):
        return gamma(S.NegativeInfinity)

    return None


handlers_dict['factorial'] = refine_factorial
