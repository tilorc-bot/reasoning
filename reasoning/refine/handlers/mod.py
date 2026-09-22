"""Refine handler for :class:`~sympy.core.mod.Mod`.

``Mod`` uses Python's convention, so ``Mod(p, q) = p - q*floor(p/q)`` for
``q != 0`` (exactly the rewrite ``Mod._eval_rewrite_as_floor``).  Because the
definition is already in terms of ``floor``, the formula is exact for every
sign of ``p`` and ``q``; no separate sign variants are needed, unlike
``Rem``.

Rules (missing-handler report section 3.6, refs #30376/#29743):

* ``Mod(p, q)`` under ``Q.integer(p/q)`` is ``0`` (the quotient is exact);
  with a literal ``q = 1`` and integer ``p`` this is the report's
  ``Mod(p, 1) -> 0`` case.
* ``Mod(p, 2)`` under ``Q.even(p)`` is ``0``, under ``Q.odd(p)`` is ``1``.
* ``Mod(p, q)`` under ``Q.integer(p) & Q.integer(q)`` is ``p - q*floor(p/q)``.
  The residual ``floor(p/q)`` is left for the vendored floor handler to
  refine (it collapses to ``p`` when ``q = 1``).

``Mod`` is undefined at ``q = 0`` (``Mod.eval`` raises); the handler does not
spend an extra ``Q.nonzero(q)`` query, so the rules hold on the domain of
definition.

No rule is applied when the corresponding query answers ``None``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic
from sympy.functions.elementary.integers import floor

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_Mod(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    p, q = expr.args
    if _upstream.ask(Q.integer(p / q), assumptions):
        return S.Zero

    if q == 2:
        if _upstream.ask(Q.even(p), assumptions):
            return S.Zero
        if _upstream.ask(Q.odd(p), assumptions):
            return S.One

    if (_upstream.ask(Q.integer(p), assumptions)
            and _upstream.ask(Q.integer(q), assumptions)):
        return p - q * floor(p / q)

    return None


handlers_dict['Mod'] = refine_Mod
