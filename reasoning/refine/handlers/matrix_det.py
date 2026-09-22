"""Refine handler for :class:`~sympy.matrices.expressions.Determinant`.

Port of ``refine_Determinant`` from
``sympy/matrices/expressions/determinant.py``.  Every predicate is asked of
the base matrix ``expr.arg``, exactly as upstream does.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_Determinant(expr: Basic, assumptions: Boolean | bool) -> Basic:
    if _upstream.ask(Q.orthogonal(expr.arg), assumptions):
        return S.One
    elif _upstream.ask(Q.singular(expr.arg), assumptions):
        return S.Zero
    elif _upstream.ask(Q.unit_triangular(expr.arg), assumptions):
        return S.One

    return expr


handlers_dict['Determinant'] = refine_Determinant
