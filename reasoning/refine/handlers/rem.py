"""Refine handler for :class:`~sympy.functions.elementary.miscellaneous.Rem`.

SymPy defines ``Rem(p, q) = p - int(p/q)*q`` (C99 truncated remainder, sign of
the dividend), *not* ``p - q*floor(p/q)`` (see ``Rem.eval``).  The two agree
only when ``p/q >= 0`` (or the division is exact), so the naive floor identity
is restricted to the sign combinations where truncation equals ``floor`` or
``ceiling``:

* ``q > 0``: ``int(p/q)`` is ``floor`` for ``p >= 0`` and ``ceil`` for ``p <= 0``.
* ``q < 0``: ``int(p/q)`` is ``ceil`` for ``p >= 0`` and ``floor`` for ``p <= 0``.

Rules (missing-handler report section 3.6):

* ``Rem(p, q)`` under ``Q.zero(p)`` is ``0``.
* ``Rem(p, q)`` under ``Q.integer(p/q)`` is ``0`` (exact division).
* the four sign-restricted integer cases above, each requiring
  ``Q.integer(p) & Q.integer(q)`` plus the signs of ``p`` and ``q``.
  With integer ``p`` and ``q`` but no sign information the expression is left
  unchanged, because no single one of the two identities is implied.

``Rem`` is undefined at ``q = 0`` (``Rem.eval`` raises); like ``Mod`` the
handler does not spend an extra ``Q.nonzero(q)`` query, so the rules hold on
the domain of definition.

No rule is applied when the corresponding query answers ``None``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sympy.assumptions import Q
from sympy.core import S, Basic
from sympy.functions.elementary.integers import ceiling, floor

from .. import _upstream
from .._upstream import handlers_dict

if TYPE_CHECKING:
    from sympy.logic.boolalg import Boolean


def refine_Rem(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    p, q = expr.args
    if _upstream.ask(Q.zero(p), assumptions):
        return S.Zero
    if _upstream.ask(Q.integer(p / q), assumptions):
        return S.Zero

    if not (_upstream.ask(Q.integer(p), assumptions)
            and _upstream.ask(Q.integer(q), assumptions)):
        return None

    p_nonnegative = _upstream.ask(Q.nonnegative(p), assumptions)
    p_nonpositive = _upstream.ask(Q.nonpositive(p), assumptions)
    q_positive = _upstream.ask(Q.positive(q), assumptions)
    q_negative = _upstream.ask(Q.negative(q), assumptions)

    if p_nonnegative and q_positive:
        return p - q * floor(p / q)
    if p_nonpositive and q_negative:
        return p - q * floor(p / q)
    if p_nonnegative and q_negative:
        return p - q * ceiling(p / q)
    if p_nonpositive and q_positive:
        return p - q * ceiling(p / q)

    return None


handlers_dict['Rem'] = refine_Rem
