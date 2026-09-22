"""Refine handler for :class:`~sympy.matrices.expressions.MatMul`.

Port of ``refine_MatMul`` from ``sympy/matrices/expressions/matmul.py``: a
factor followed by its transpose cancels to an identity when the factor is
orthogonal, and a factor followed by its conjugate cancels when it is
unitary.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sympy.assumptions import Q
from sympy.core import Basic
from sympy.matrices.expressions import Identity, MatMul

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_MatMul(expr: Basic, assumptions: Boolean | bool) -> Basic:
    newargs: list[Any] = []
    exprargs: list[Any] = []

    for arg in expr.args:
        if arg.is_Matrix:
            exprargs.append(arg)
        else:
            newargs.append(arg)

    last = exprargs[0]
    for arg in exprargs[1:]:
        if arg == last.T and _upstream.ask(Q.orthogonal(arg), assumptions):
            last = Identity(arg.shape[0])
        elif arg == last.conjugate() and _upstream.ask(Q.unitary(arg),
                                                       assumptions):
            last = Identity(arg.shape[0])
        else:
            newargs.append(last)
            last = arg
    newargs.append(last)

    return MatMul(*newargs)


handlers_dict['MatMul'] = refine_MatMul
