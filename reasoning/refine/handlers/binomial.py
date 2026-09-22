"""Refine handler for :class:`~sympy.functions.combinatorial.factorials.binomial`.

Rules (missing-handler report section 3.6, ref #29213):

* ``binomial(n, k)`` under ``Q.zero(k)`` is ``1``.
* ``binomial(n, k)`` under ``Q.eq(k, 1)`` is ``n``.
* ``binomial(n, k)`` under ``Q.integer(k) & Q.negative(k)`` is ``0``.
* ``binomial(n, k)`` under ``Q.integer(n) & Q.nonnegative(n) & Q.integer(k) &
  Q.negative(n - k)`` is ``0`` (``k`` exceeds the nonnegative integer support).

The last rule is quoted in the report without ``Q.integer(k)``; that is not
sound (``binomial(2, 3/2) = 16/(3*pi)``), so the integer constraint on ``k``
is required here.

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


def refine_binomial(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    n, k = expr.args
    if _upstream.ask(Q.zero(k), assumptions):
        return S.One
    if _upstream.ask(Q.eq(k, 1), assumptions):
        return n
    if _upstream.ask(Q.integer(k) & Q.negative(k), assumptions):
        return S.Zero
    if (_upstream.ask(Q.integer(n), assumptions)
            and _upstream.ask(Q.nonnegative(n), assumptions)
            and _upstream.ask(Q.integer(k), assumptions)
            and _upstream.ask(Q.negative(n - k), assumptions)):
        return S.Zero

    return None


handlers_dict['binomial'] = refine_binomial
