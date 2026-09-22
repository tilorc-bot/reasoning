"""Refine handler for ``sinc``.

``sinc(0) = 1`` by construction, but a symbolic argument that is only known
to be zero through the assumptions stays unevaluated and is reduced here.
No other simplification is defined for ``sinc``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_sinc(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    arg = expr.args[0]
    if _upstream.ask(Q.zero(arg), assumptions):
        return S.One
    return expr


handlers_dict['sinc'] = refine_sinc
