"""Refine handler for the natural logarithm.

Rules (agent report section 3.3, upstream PRs #29131/#29760):

* ``log(exp(x)) -> x`` when ``x`` is real (the branch-cut guard: for complex
  ``x`` the principal logarithm does not invert the exponential);
* ``log(x**y) -> y*log(x)`` when ``x`` is positive and ``y`` is real (this
  covers ``log(1/x) -> -log(x)`` and ``log(x**2) -> 2*log(x)``; a merely real
  base is not enough, so ``log(x**2)`` stays put under ``Q.real(x)``);
* ``log(x*y) -> log(x) + log(y)`` when every factor is positive.

Every rule is skipped when the engine answers ``None``; the handler then
returns ``None`` so the dispatcher leaves the expression unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Add, Basic, Mul, Pow

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_log(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    from sympy.functions.elementary.exponential import exp, log

    arg = expr.args[0]

    if isinstance(arg, exp):
        if _upstream.ask(Q.real(arg.args[0]), assumptions):
            return arg.args[0]

    if isinstance(arg, Pow):
        base, exponent = arg.base, arg.exp
        if (_upstream.ask(Q.positive(base), assumptions)
                and _upstream.ask(Q.real(exponent), assumptions)):
            return exponent * log(base)

    if isinstance(arg, Mul):
        if all(_upstream.ask(Q.positive(factor), assumptions)
               for factor in arg.args):
            return Add(*[log(factor) for factor in arg.args])

    return None


handlers_dict['log'] = refine_log
