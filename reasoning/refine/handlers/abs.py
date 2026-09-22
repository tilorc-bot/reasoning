"""Refine handler for :class:`~sympy.functions.elementary.complexes.Abs`.

Overrides the vendored ``refine_abs`` only to add the zero case: ``Abs(x)`` is
``0`` under ``Q.zero(x)``, where the vendored handler returned ``x`` (agent
report section 3.5).  All other behavior (positive/negative arguments and the
``Mul`` factor split) is delegated unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_abs(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    arg = expr.args[0]
    if _upstream.ask(Q.zero(arg), assumptions):
        return S.Zero
    return _upstream.refine_abs(expr, assumptions)


handlers_dict['Abs'] = refine_abs
