"""Refine handlers for ``RisingFactorial`` and ``FallingFactorial``.

Rules (missing-handler report section 3.6):

* ``rf(x, k)`` and ``ff(x, k)`` under ``Q.zero(k)`` are ``1`` (empty product).
* ``rf(0, k)`` and ``ff(0, k)`` under ``Q.zero(x) & Q.positive(k) &
  Q.integer(k)`` are ``0``: the product contains the factor ``0``.
* ``ff(x, x)`` under ``Q.integer(x)`` is ``factorial(x)``.  SymPy applies the
  same rewrite in ``FallingFactorial.eval`` as soon as ``x == k`` is a literal
  integer; the handler makes it depend on the assumption instead.

No rule is applied when the corresponding query answers ``None``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic
from sympy.functions.combinatorial.factorials import factorial

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def _is_positive_integer(k: Basic, assumptions: Boolean | bool) -> bool | None:
    if not _upstream.ask(Q.integer(k), assumptions):
        return False
    return _upstream.ask(Q.positive(k), assumptions)


def refine_RisingFactorial(
    expr: Basic, assumptions: Boolean | bool
) -> Basic | None:
    x, k = expr.args
    if _upstream.ask(Q.zero(k), assumptions):
        return S.One
    if (_upstream.ask(Q.zero(x), assumptions)
            and _is_positive_integer(k, assumptions)):
        return S.Zero

    return None


def refine_FallingFactorial(
    expr: Basic, assumptions: Boolean | bool
) -> Basic | None:
    x, k = expr.args
    if _upstream.ask(Q.zero(k), assumptions):
        return S.One
    if x == k and _upstream.ask(Q.integer(x), assumptions):
        return factorial(x)
    if (_upstream.ask(Q.zero(x), assumptions)
            and _is_positive_integer(k, assumptions)):
        return S.Zero

    return None


handlers_dict['RisingFactorial'] = refine_RisingFactorial
handlers_dict['FallingFactorial'] = refine_FallingFactorial
