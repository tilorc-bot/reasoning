"""Refine handler for the fractional part :class:`~sympy.functions.elementary.integers.frac`.

Rules (missing-handler report section 3.6, refs #30368/#29744):

* ``frac(x)`` under ``Q.integer(x)`` is ``0``.
* ``frac(x + n)`` under ``Q.integer(n)`` is ``frac(x)``; more generally every
  integer addend of ``x + y + ...`` is dropped and the remaining non-integer
  addends are kept inside a single ``frac`` (``frac`` is unchanged by adding
  an integer).  If every addend is an integer the result is ``0``.

No rule is applied when the corresponding query answers ``None``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Add, Basic
from sympy.functions.elementary.integers import frac

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_frac(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    arg = expr.args[0]
    if _upstream.ask(Q.integer(arg), assumptions):
        return S.Zero

    if isinstance(arg, Add):
        non_integer_terms = [
            term
            for term in arg.args
            if not _upstream.ask(Q.integer(term), assumptions)
        ]
        if len(non_integer_terms) != len(arg.args):
            if not non_integer_terms:
                return S.Zero
            return frac(Add(*non_integer_terms))

    return None


handlers_dict['frac'] = refine_frac
