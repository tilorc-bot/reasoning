"""Refine handler for :class:`~sympy.functions.special.tensor_functions.KroneckerDelta`.

Rules (missing-handler report section 3.12):

* ``KroneckerDelta(i, j)`` under ``Q.eq(i, j)`` is ``1``.
* ``KroneckerDelta(i, j)`` under ``Q.ne(i, j)`` is ``0``.

Equality is never assumed: both queries must answer ``True`` explicitly, so an
unknown or merely related assumption (for example ``Q.eq(i, k)``) leaves the
expression unchanged.  The engine derives no ``Q.ne`` from a given ``Q.eq``,
but the ``Q.ne`` direction is reachable when that assumption is stated
directly.  Folded multi-argument deltas are left alone.

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


def refine_KroneckerDelta(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    args = expr.args
    if len(args) != 2:
        return None
    i, j = args
    if _upstream.ask(Q.eq(i, j), assumptions):
        return S.One
    if _upstream.ask(Q.ne(i, j), assumptions):
        return S.Zero
    return None


handlers_dict['KroneckerDelta'] = refine_KroneckerDelta
