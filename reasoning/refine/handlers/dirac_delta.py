"""Refine handler for :class:`~sympy.functions.special.delta_functions.DiracDelta`.

Rule (missing-handler report section 3.12): ``DiracDelta(x)`` under
``Q.nonzero(x)`` is ``0``.  ``DiracDelta(x, k)`` is the ``k``-th derivative of
the delta, so it vanishes for the same arguments; only the first argument is
queried, and an assumption about the derivative order changes nothing.

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


def refine_DiracDelta(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    arg = expr.args[0]
    if _upstream.ask(Q.nonzero(arg), assumptions):
        return S.Zero
    return None


handlers_dict['DiracDelta'] = refine_DiracDelta
