"""Refine handler for :class:`~sympy.matrices.expressions.matexpr.MatrixElement`.

Extends the vendored ``refine_matrixelement`` with two rules: an element of a
matrix known to be zero is zero, and an off-diagonal element of a matrix known
to be diagonal is zero when the indices are provably distinct.  The vendored
symmetric-index swap is kept by delegating to
:func:`~reasoning.refine._upstream.refine_matrixelement` when neither new rule
applies.

Indices count as provably distinct only when the difference is structurally
nonzero (unequal integer literals, offset indices such as ``i`` and ``i + 1``)
or when ``Q.ne(i, j)`` follows from the assumptions.  Independent symbols are
not distinct: ``X[i, j]`` is on the diagonal when ``i == j``, so no zero can
be proved without an explicit disequality.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict, refine_matrixelement

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def _provably_distinct(i: Basic, j: Basic,
                       assumptions: Boolean | bool) -> bool:
    """Whether the element indices ``i`` and ``j`` can be shown to differ."""
    if (i - j).is_nonzero is True:
        return True
    return _upstream.ask(Q.ne(i, j), assumptions) is True


def refine_MatrixElement(expr: Basic,
                         assumptions: Boolean | bool) -> Basic | None:
    matrix, i, j = expr.args
    if _upstream.ask(Q.zero(matrix), assumptions):
        return S.Zero
    if (_upstream.ask(Q.diagonal(matrix), assumptions)
            and _provably_distinct(i, j, assumptions)):
        return S.Zero
    return refine_matrixelement(expr, assumptions)


handlers_dict['MatrixElement'] = refine_MatrixElement
