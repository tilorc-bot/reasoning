"""Refine handler for :class:`~sympy.functions.special.gamma_functions.gamma`.

Rule (missing-handler report section 3.7, ref #29203): ``gamma(n)`` under
``Q.integer(n) & Q.nonpositive(n)`` is ``zoo``; ``gamma`` has a pole at every
nonpositive integer.  Exact constants (``gamma(0)``, ``gamma(-1)``, ...)
already evaluate at construction.

No rule is applied when the corresponding query answers ``None``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_gamma(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    arg = expr.args[0]
    if _upstream.ask(Q.integer(arg) & Q.nonpositive(arg), assumptions):
        return S.ComplexInfinity
    return None


handlers_dict['gamma'] = refine_gamma
