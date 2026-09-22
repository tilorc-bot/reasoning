"""Refine handler for :class:`~sympy.matrices.expressions.Trace`.

SymPy has no upstream ``Trace`` handler; the rule implemented here is that
the trace of a matrix known to be zero is zero.  Any other assumption (or an
unknown answer) leaves the trace untouched.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_Trace(expr: Basic, assumptions: Boolean | bool) -> Basic:
    if _upstream.ask(Q.zero(expr.arg), assumptions):
        return S.Zero
    return expr


handlers_dict['Trace'] = refine_Trace
