"""Refine handlers for the complex conjugate and conjugate-pair products.

Basic rules only (agent report section 3.5, upstream PR #29173 basic half):

* ``conjugate(x) -> x`` when ``x`` is real;
* ``conjugate(x) -> -x`` when ``x`` is imaginary;
* ``conjugate(x**n) -> conjugate(x)**n`` when ``n`` is an integer and ``x`` is
  complex, which under ``Q.imaginary(x)`` refines further to ``(-x)**n``;
* ``z*conjugate(z) -> Abs(z)**2``.

The last rule acts on products, so this module also registers the auxiliary
registry key ``Mul`` (the dispatcher is keyed on the top-level class name and a
``conjugate`` handler never sees the enclosing product).  Branch-cut-heavy
conjugate rules for ``log``/inverse trigonometric functions are deliberately
not implemented here; they are a deferred research item.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import Basic, Mul, Pow
from sympy.functions.elementary.complexes import Abs, conjugate

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_conjugate(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    arg = expr.args[0]

    if _upstream.ask(Q.real(arg), assumptions):
        return arg
    if _upstream.ask(Q.imaginary(arg), assumptions):
        return -arg

    if isinstance(arg, Pow):
        base, exponent = arg.base, arg.exp
        if (_upstream.ask(Q.integer(exponent), assumptions)
                and _upstream.ask(Q.complex(base), assumptions)):
            return conjugate(base) ** exponent

    return None


def refine_Mul(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    """Cancel conjugate pairs in a product: ``z*conjugate(z) -> Abs(z)**2``."""
    factors = expr.args
    conjugates = [factor for factor in factors
                  if isinstance(factor, conjugate)]
    if not conjugates:
        return None

    result = [factor for factor in factors if not isinstance(factor, conjugate)]
    paired = False
    for factor in conjugates:
        arg = factor.args[0]
        if arg in result:
            result.remove(arg)
            result.append(Abs(arg) ** 2)
            paired = True
        else:
            result.append(factor)

    if not paired:
        return None
    return Mul(*result)


handlers_dict['conjugate'] = refine_conjugate
handlers_dict['Mul'] = refine_Mul
