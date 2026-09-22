"""Refine handler for :class:`~sympy.matrices.expressions.MatAdd`.

SymPy has no upstream ``MatAdd`` handler; the rule implemented here drops
terms whose matrix is known to be zero.  A single surviving term is returned
directly (``MatAdd(X)`` is not the same object as ``X``) and an all-zero sum
collapses to the ``ZeroMatrix`` of the sum's shape (``MatAdd()`` would give
the bare ``GenericZeroMatrix`` instead).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Basic
from sympy.matrices.expressions import MatAdd, ZeroMatrix

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_MatAdd(expr: Basic, assumptions: Boolean | bool) -> Basic:
    kept = [term for term in expr.args
            if not _upstream.ask(Q.zero(term), assumptions)]
    if len(kept) == len(expr.args):
        return expr
    if not kept:
        return ZeroMatrix(*expr.shape)
    if len(kept) == 1:
        return kept[0]
    return MatAdd(*kept)


handlers_dict['MatAdd'] = refine_MatAdd
