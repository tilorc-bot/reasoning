"""Shared ``pi/2`` coefficient parsing for the trigonometric handlers.

The parser mirrors the pre-processing that :func:`refine_sin_cos` performs
before it decides on a phase shift: every term of the argument that is an
integer multiple of ``pi/2`` is split into a part whose half-coefficient
parity is known and a part whose parity is not, and everything else is left
alone.  Handlers for ``tan``, ``cot``, ``sec`` and ``csc`` use the same split
so they agree with ``sin``/``cos`` on what counts as a known shift.
"""
from __future__ import annotations

from typing import Any, NamedTuple

from sympy.assumptions import Q
from sympy.core import S

from .. import _upstream


class PiHalfSplit(NamedTuple):
    """A parsed ``pi/2`` decomposition of a trigonometric argument.

    ``known_sum`` and ``unknown_sum`` are sums of coefficients expressed in
    units of ``pi/2`` (matching ``2 * term.coeff(pi)`` in
    :func:`refine_sin_cos`); ``known_sum_is_even`` is the parity of
    ``known_sum``.  ``remaining_terms`` are the argument terms that are not
    known integer multiples of ``pi/2``.
    """

    known_sum: Any
    known_sum_is_even: bool
    unknown_sum: Any
    remaining_terms: tuple[Any, ...]


def parity(expr: Any, assumptions: Any = True) -> bool | None:
    """Return the parity of ``expr`` through the vendored ask, or ``None``."""
    return _upstream.ask(Q.even(expr), assumptions)


def split_pi_half(arg: Any, assumptions: Any = True) -> PiHalfSplit | None:
    """Split ``arg`` into known/unknown ``pi/2`` shifts.

    Returns ``None`` when ``arg`` has no term that is a known integer multiple
    of ``pi/2``, or when the parity-known coefficients sum to zero; both cases
    mean no phase reduction is possible.
    """
    terms = arg.args if arg.is_Add else (arg,)
    known_coeffs: list[Any] = []
    unknown_coeffs: list[Any] = []
    remaining_terms: list[Any] = []
    for term in terms:
        coeff_of_pi = term.coeff(S.Pi)
        if coeff_of_pi and _upstream.ask(Q.integer(2 * coeff_of_pi),
                                         assumptions):
            coeff_of_pi_half = 2 * coeff_of_pi
            coeff_is_even = parity(coeff_of_pi_half, assumptions)
            if coeff_is_even is None:
                unknown_coeffs.append(coeff_of_pi_half)
            else:
                known_coeffs.append((coeff_of_pi_half, coeff_is_even))
        else:
            remaining_terms.append(term)

    if not known_coeffs:
        return None

    known_sum = 0
    known_sum_is_even = True
    for coeff, coeff_is_even in known_coeffs:
        known_sum += coeff
        known_sum_is_even = known_sum_is_even == coeff_is_even
    if known_sum == 0:
        return None

    return PiHalfSplit(
        known_sum=known_sum,
        known_sum_is_even=known_sum_is_even,
        unknown_sum=sum(unknown_coeffs) if unknown_coeffs else S.Zero,
        remaining_terms=tuple(remaining_terms),
    )


def remainder(split: PiHalfSplit) -> Any:
    """Rebuild the argument with the parity-known ``pi/2`` shift removed."""
    return sum(split.remaining_terms) + split.unknown_sum * S.Pi / 2
