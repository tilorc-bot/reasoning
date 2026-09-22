"""Refine handler for :class:`~sympy.matrices.expressions.matexpr.MatrixElement`.

Extends the vendored ``refine_matrixelement`` with two rules: an element of a
matrix known to be zero is zero, and an off-diagonal element of a matrix known
to be diagonal is zero when the indices are provably distinct.  The vendored
symmetric-index swap is kept by delegating to
:func:`~reasoning.refine._upstream.refine_matrixelement` when neither new rule
applies.

Indices count as provably distinct when both are integer literals and differ,
or when both are non-integer expressions whose difference looks negative
(``could_extract_minus_sign``, the same heuristic the vendored symmetric swap
uses).  A mixed literal/symbolic pair is never treated as distinct: e.g.
``X[0, i]`` is on the diagonal when ``i`` is zero, so no zero can be proved.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict, refine_matrixelement

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def _provably_distinct(i: Basic, j: Basic) -> bool:
    """Whether the element indices ``i`` and ``j`` can be shown to differ."""
    if i.is_Integer and j.is_Integer:
        return bool(i != j)
    if not i.is_Integer and not j.is_Integer:
        return bool((i - j).could_extract_minus_sign())
    return False


def refine_MatrixElement(expr: Basic,
                         assumptions: Boolean | bool) -> Basic | None:
    matrix, i, j = expr.args
    if _upstream.ask(Q.zero(matrix), assumptions):
        return S.Zero
    if (_upstream.ask(Q.diagonal(matrix), assumptions)
            and _provably_distinct(i, j)):
        return S.Zero
    return refine_matrixelement(expr, assumptions)


handlers_dict['MatrixElement'] = refine_MatrixElement
