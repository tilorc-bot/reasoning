"""Refine handler for :class:`~sympy.matrices.expressions.Inverse`.

Port of ``refine_Inverse`` from ``sympy/matrices/expressions/inverse.py``.
The upstream handler asks ``Q.orthogonal(expr)``/``Q.unitary(expr)``; the
independent engine cannot derive the inverse closure from predicates on the
base matrix, so the port asks ``expr.arg`` instead.  As upstream does, the
``Q.singular`` branch raises :class:`ValueError`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_Inverse(expr: Basic, assumptions: Boolean | bool) -> Basic:
    if _upstream.ask(Q.orthogonal(expr.arg), assumptions):
        return expr.arg.T
    elif _upstream.ask(Q.unitary(expr.arg), assumptions):
        return expr.arg.conjugate()
    elif _upstream.ask(Q.singular(expr.arg), assumptions):
        raise ValueError("Inverse of singular matrix %s" % expr.arg)

    return expr


handlers_dict['Inverse'] = refine_Inverse
