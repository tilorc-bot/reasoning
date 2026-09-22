"""Refine handler for :class:`~sympy.matrices.expressions.HadamardProduct`.

SymPy has no upstream ``HadamardProduct`` handler; the rule implemented here
is that an elementwise product with a factor known to be zero is the
``ZeroMatrix`` of the product's shape.  Identity factors are deliberately not
handled: ``HadamardProduct`` with an ``Identity`` or ``OneMatrix`` factor is
not generally simplifiable under assumptions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Basic
from sympy.matrices.expressions import ZeroMatrix

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_HadamardProduct(expr: Basic,
                           assumptions: Boolean | bool) -> Basic:
    for factor in expr.args:
        if _upstream.ask(Q.zero(factor), assumptions):
            return ZeroMatrix(*expr.shape)
    return expr


handlers_dict['HadamardProduct'] = refine_HadamardProduct
