"""Refine handler for :class:`~sympy.core.power.Pow`.

The nested-power casework replaces the vendored ``refine_Pow`` branch that
unconditionally rewrote ``(z1**z2)**z3`` (with rational ``z3``) to
``Abs(z1)**(z2*z3)``.  That rewrite is wrong: ``(x**3)**(1/2)`` is
``Abs(x)**(3/2)`` only at nonnegative ``x``, not under ``Q.real(x)`` (issue
#29684, upstream PR #29800).  The valid cases are:

* ``z3`` integer          -> ``z1**(z2*z3)``;
* ``z1`` positive and ``z2`` real -> ``z1**(z2*z3)``;
* ``z1`` real and ``z2`` even     -> ``Abs(z1)**(z2*z3)``.

Other rules fixed/added here:

* ``Abs(z)**n -> (-1)**(n/2) * z**n`` for imaginary ``z`` and even ``n``
  (so ``Abs(z)**2 -> -z**2`` and ``Abs(z)**4 -> z**4``; issues #30473,
  upstream PRs #30474/#30476);
* ``Pow(E, x)`` (an unevaluated power) is delegated to ``refine_exp`` instead
  of duplicating the phase logic (upstream PR #30248).

Everything else, including the ``(-1)**Add`` machinery, is delegated to
``_upstream.refine_Pow``.  The one vendored branch that is never delegated to
is the buggy nested-power rewrite, because ``base`` being a ``Pow`` is exactly
its precondition.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic, Pow

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_Pow(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    from sympy.functions.elementary.complexes import Abs
    from sympy.functions.elementary.exponential import exp

    base = expr.base

    if isinstance(base, Abs):
        arg = base.args[0]
        if (_upstream.ask(Q.imaginary(arg), assumptions)
                and _upstream.ask(Q.even(expr.exp), assumptions)):
            return (-S.One) ** (expr.exp / 2) * arg ** expr.exp
        return _upstream.refine_Pow(expr, assumptions)

    if isinstance(base, Pow):
        inner_base, inner_exp = base.base, base.exp
        outer_exp = expr.exp
        if _upstream.ask(Q.integer(outer_exp), assumptions):
            return inner_base ** (inner_exp * outer_exp)
        if (_upstream.ask(Q.positive(inner_base), assumptions)
                and _upstream.ask(Q.real(inner_exp), assumptions)):
            return inner_base ** (inner_exp * outer_exp)
        if (_upstream.ask(Q.real(inner_base), assumptions)
                and _upstream.ask(Q.even(inner_exp), assumptions)):
            return Abs(inner_base) ** (inner_exp * outer_exp)
        return None

    if base is S.Exp1:
        phase = exp(expr.exp)
        if isinstance(phase, exp):
            refined = _upstream.refine_exp(phase, assumptions)
            if refined != phase:
                return refined
        return _upstream.refine_Pow(expr, assumptions)

    return _upstream.refine_Pow(expr, assumptions)


handlers_dict['Pow'] = refine_Pow
