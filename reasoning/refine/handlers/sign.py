"""Refine handler for :class:`~sympy.functions.elementary.complexes.sign`.

The vendored ``refine_sign`` asks ``Q.real(arg)`` and ``Q.imaginary(arg)``
without passing ``assumptions`` (upstream bug fixed by PR #29605), so
``refine(sign(x), Q.positive(x))`` returned ``sign(x)`` for a plain symbol
instead of ``1``.  This copy passes the assumptions through; it is otherwise
identical to the vendored function.

Old-assumption symbols (``Symbol('x', imaginary=True)``) are still not seen by
the independent engine, so the imaginary branch stays blocked until an
old-assumption bridge exists.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_sign(expr: Basic, assumptions: Boolean | bool) -> Basic:
    arg = expr.args[0]

    if _upstream.ask(Q.zero(arg), assumptions):
        return S.Zero
    if _upstream.ask(Q.real(arg), assumptions):
        if _upstream.ask(Q.positive(arg), assumptions):
            return S.One
        if _upstream.ask(Q.negative(arg), assumptions):
            return S.NegativeOne
    if _upstream.ask(Q.imaginary(arg), assumptions):
        arg_re, arg_im = arg.as_real_imag()
        if _upstream.ask(Q.positive(arg_im), assumptions):
            return S.ImaginaryUnit
        if _upstream.ask(Q.negative(arg_im), assumptions):
            return -S.ImaginaryUnit
    return expr


handlers_dict['sign'] = refine_sign
