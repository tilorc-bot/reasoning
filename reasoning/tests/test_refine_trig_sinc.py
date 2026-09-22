"""Tests for the ``sinc`` refine handler."""
from __future__ import annotations

from sympy.assumptions import Q
from sympy.abc import x
from sympy.functions.elementary.trigonometric import sinc

from reasoning.refine import refine
from reasoning.tests.refine_harness import (
    assert_refinement_valid,
    stub_ask,
    use_ask,
)


def test_zero_argument() -> None:
    assert refine(sinc(x), Q.zero(x)) == 1
    assert_refinement_valid(sinc(x), Q.zero(x), 1)


def test_nonzero_argument_unchanged() -> None:
    assert refine(sinc(x), Q.nonzero(x)) == sinc(x)
    assert refine(sinc(x), Q.real(x)) == sinc(x)


def test_none_safe() -> None:
    with use_ask(stub_ask({})):
        assert refine(sinc(x), Q.zero(x)) == sinc(x)
