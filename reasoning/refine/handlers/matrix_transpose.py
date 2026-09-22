"""Refine handler for :class:`~sympy.matrices.expressions.Transpose`.

Port of ``refine_Transpose`` from
``sympy/matrices/expressions/transpose.py``.  The upstream handler asks
``Q.symmetric(expr)``; the independent engine cannot derive the transpose
closure ``Q.symmetric(X.T)`` from ``Q.symmetric(X)``, so the port asks the
base matrix ``expr.arg`` instead.  Under SymPy's own ``ask`` the reference
comparison still holds, because SymPy derives both directions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_Transpose(expr: Basic, assumptions: Boolean | bool) -> Basic:
    if _upstream.ask(Q.symmetric(expr.arg), assumptions):
        return expr.arg

    return expr


handlers_dict['Transpose'] = refine_Transpose
