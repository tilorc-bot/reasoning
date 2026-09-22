"""Unit tests for the shared ``pi/2`` parser in ``handlers/_trig.py``."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import m, n, x
from sympy.core.singleton import S
from sympy.functions.elementary.trigonometric import cos, sin

from reasoning.refine.handlers import _trig
from reasoning.tests.refine_harness import stub_ask, use_ask


def test_non_add_pi_multiple() -> None:
    split = _trig.split_pi_half(n * S.Pi, Q.integer(n))
    assert split is not None
    assert split.known_sum == 2 * n
    assert split.known_sum_is_even is True
    assert split.unknown_sum == S.Zero
    assert split.remaining_terms == ()
    assert _trig.remainder(split) == S.Zero


def test_add_with_unknown_and_non_pi_terms() -> None:
    arg = x + n * S.Pi + m * S.Pi
    split = _trig.split_pi_half(arg, Q.integer(n))
    assert split is not None
    assert split.known_sum == 2 * n
    assert split.known_sum_is_even is True
    assert split.remaining_terms == (x, m * S.Pi)
    assert _trig.remainder(split) == x + m * S.Pi


def test_unknown_parity_alone_yields_none() -> None:
    fake = stub_ask({str(Q.integer(2 * n)): True, str(Q.even(2 * n)): None})
    with use_ask(fake):
        assert _trig.split_pi_half(n * S.Pi, Q.integer(n)) is None


def test_unknown_parity_goes_to_unknown_sum() -> None:
    fake = stub_ask({
        str(Q.integer(2 * n)): True,
        str(Q.even(2 * n)): True,
        str(Q.integer(2 * m)): True,
        str(Q.even(2 * m)): None,
    })
    with use_ask(fake):
        split = _trig.split_pi_half(n * S.Pi + m * S.Pi, True)
    assert split is not None
    assert split.known_sum == 2 * n
    assert split.known_sum_is_even is True
    assert split.unknown_sum == 2 * m
    assert _trig.remainder(split) == m * S.Pi


def test_non_pi_multiple_yields_none() -> None:
    assert _trig.split_pi_half(x, Q.real(x)) is None
    assert _trig.split_pi_half(sin(x) + cos(x), Q.real(x)) is None


def test_parity() -> None:
    assert _trig.parity(2 * n, Q.integer(n)) is True
    assert _trig.parity(n, True) is None
