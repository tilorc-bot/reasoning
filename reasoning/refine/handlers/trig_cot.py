"""Refine handler for ``cot``.

Upstream SymPy has no ``cot`` handler; the rules mirror the ``refine_tan_cot``
proposal of PR #29324 and reuse the shared ``pi/2`` parser of :mod:`._trig`.
``cot`` has period ``pi``, so only the parity of a known ``pi/2`` shift
matters: an even shift is the identity, an odd shift swaps ``cot`` for
``-tan``.  A pure odd multiple of ``pi/2`` reduces to ``-tan(0) = 0``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict
from ._trig import remainder, split_pi_half

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_cot(expr: Basic, assumptions: Boolean | bool = True) -> Basic | None:
    from sympy.functions.elementary.trigonometric import tan

    arg = expr.args[0]
    if _upstream.ask(Q.zero(arg), assumptions):
        return S.ComplexInfinity

    split = split_pi_half(arg, assumptions)
    if split is None:
        return expr

    rem = remainder(split)
    if split.known_sum_is_even:
        return expr.func(rem)
    return -tan(rem)


handlers_dict['cot'] = refine_cot
