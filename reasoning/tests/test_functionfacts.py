from __future__ import annotations

import importlib

import pytest
from sympy.assumptions.ask import Q
from sympy.core.numbers import I, Rational, pi
from sympy.core.parameters import _exp_is_pow
from sympy.core.singleton import S
from sympy.functions.combinatorial.factorials import factorial
from sympy.functions.elementary.complexes import Abs, im, re, sign
from sympy.functions.elementary.exponential import exp, log
from sympy.functions.elementary.trigonometric import (
    acos, acot, asin, atan, cos, cot, sin, tan,
)
from sympy.abc import p, x, y

from reasoning.clauses import Formula, iter_atoms
from reasoning.functionfacts import register_function_facts
from reasoning.predicates import AppliedPredicate as LocalAppliedPredicate
from reasoning.predicates import Q as LocalQ
from reasoning.registry import ClassFactRegistry
from reasoning.satask import satask
from reasoning.sathandlers import class_fact_registry

oo = S.Infinity


def test_trigonometric_real_and_finite_facts() -> None:
    assert satask(Q.real(sin(x))) is None
    assert satask(Q.real(sin(x)), Q.real(x)) is True
    assert satask(Q.real(cos(x)), Q.real(x)) is True

    assert satask(Q.finite(sin(x))) is True
    assert satask(Q.finite(sin(x)), ~Q.finite(x)) is True
    assert satask(Q.finite(cos(x))) is True
    assert satask(Q.finite(cos(x)), ~Q.finite(x)) is True

    assert satask(Q.complex(sin(x))) is True
    assert satask(Q.complex(cos(x))) is True


def test_exponential_facts() -> None:
    assert satask(Q.real(exp(x))) is None
    assert satask(Q.real(exp(x)), Q.real(x)) is True
    assert satask(Q.positive(exp(x)), Q.real(x)) is True
    assert satask(~Q.negative(exp(x)), Q.real(x)) is True
    assert satask(Q.positive(exp(x)), Q.imaginary(x)) is None

    assert satask(Q.real(exp(2*pi*I, evaluate=False))) is True
    assert satask(Q.real(exp(pi*I, evaluate=False))) is True
    assert satask(Q.real(exp(pi*I/2, evaluate=False))) is False
    assert satask(Q.positive(exp(2*pi*I, evaluate=False))) is True
    assert satask(Q.negative(exp(pi*I, evaluate=False))) is True
    assert satask(Q.imaginary(exp(pi*I/2, evaluate=False))) is True
    assert satask(Q.imaginary(exp(2*pi*I, evaluate=False))) is False

    assert satask(Q.positive(exp(x*pi*I)), Q.even(x)) is True
    assert satask(Q.positive(exp(x*pi*I)), Q.odd(x)) is False
    assert satask(Q.positive(exp(x*pi*I)), Q.real(x)) is None

    assert satask(Q.finite(exp(x))) is None
    assert satask(Q.finite(exp(x)), Q.finite(x)) is True
    assert satask(Q.finite(exp(2))) is True

    assert satask(Q.algebraic(exp(0, evaluate=False))) is True
    assert satask(Q.algebraic(exp(7))) is False
    assert satask(Q.algebraic(exp(x)), Q.algebraic(x)) is None
    assert satask(Q.algebraic(exp(x)), Q.algebraic(x) & Q.nonzero(x)) is False


def test_exp_is_pow_representation() -> None:
    with _exp_is_pow(True):
        assert satask(Q.real(exp(x)), Q.real(x)) is True
        assert satask(Q.real(exp(pi*I/2, evaluate=False))) is False
        assert satask(Q.positive(exp(x)), Q.real(x)) is True
        assert satask(Q.positive(exp(x*pi*I)), Q.even(x)) is True


def test_logarithm_facts() -> None:
    assert satask(Q.real(log(x)), Q.positive(x)) is True
    assert satask(Q.real(log(x)), Q.imaginary(x)) is False
    assert satask(Q.real(log(x)), Q.complex(x)) is None
    assert satask(Q.real(log(2*I))) is False
    assert satask(Q.real(log(I))) is False

    assert satask(Q.positive(log(x)), Q.positive(x)) is None
    assert satask(Q.positive(log(x)), Q.negative(x)) is False
    assert satask(Q.positive(log(x)), Q.imaginary(x)) is False
    assert satask(Q.positive(log(x + 2)), Q.positive(x)) is True

    assert satask(Q.finite(log(x))) is None
    assert satask(Q.finite(log(x)), Q.zero(x)) is False
    assert satask(Q.finite(log(x)), Q.infinite(x)) is False
    assert satask(Q.finite(log(x)), Q.finite(x)) is None

    assert satask(Q.algebraic(log(7))) is False
    assert satask(Q.algebraic(log(1, evaluate=False))) is True


def test_absolute_value_and_parts_facts() -> None:
    assert satask(Q.positive(Abs(x))) is None
    assert satask(Q.positive(Abs(x)), Q.positive(x)) is True
    assert satask(Q.positive(Abs(x)), Q.negative(x)) is True
    assert satask(Q.nonzero(Abs(x)), Q.nonzero(x)) is True
    assert satask(Q.complex(Abs(x))) is True

    assert satask(Q.real(re(x))) is True
    assert satask(Q.real(im(x))) is True
    assert satask(Q.complex(re(x))) is True
    assert satask(Q.complex(im(x))) is True
    assert satask(Q.even(re(x)), Q.even(x)) is True
    assert satask(Q.even(im(x)), Q.even(x)) is True
    assert satask(Q.even(im(x)), Q.real(x)) is True


def test_inverse_trigonometric_facts() -> None:
    assert satask(Q.positive(atan(p)), Q.positive(p)) is True
    assert satask(Q.positive(atan(p)), Q.negative(p)) is False
    assert satask(Q.positive(atan(p)), Q.zero(p)) is False
    assert satask(Q.positive(atan(x))) is None

    assert satask(Q.positive(asin(p)), Q.positive(p)) is None
    assert satask(Q.positive(asin(Rational(1, 7)))) is True
    assert satask(Q.positive(asin(x)), Q.positive(x) & Q.nonpositive(x - 1)) is True
    assert satask(Q.positive(asin(x)), Q.negative(x) & Q.nonnegative(x + 1)) is False

    assert satask(Q.positive(acos(p)), Q.positive(p)) is None
    assert satask(Q.positive(acos(Rational(1, 7)))) is True
    assert satask(
        Q.positive(acos(x)),
        Q.nonnegative(x + 1) & Q.nonpositive(x - 1)) is True
    assert satask(Q.positive(acos(x)), Q.nonnegative(x - 1)) is None

    assert satask(Q.positive(acot(x)), Q.positive(x)) is True
    assert satask(Q.positive(acot(x)), Q.real(x)) is True
    assert satask(Q.positive(acot(x)), Q.imaginary(x)) is False
    assert satask(Q.positive(acot(x))) is None


def test_transcendental_function_arguments() -> None:
    for function in (exp, sin, tan, asin, atan, cos):
        assert satask(Q.algebraic(function(7))) is False
        assert satask(Q.algebraic(function(0, evaluate=False))) is True
        assert satask(Q.algebraic(function(x)), Q.algebraic(x)) is None
        assert satask(
            Q.algebraic(function(x)), Q.algebraic(x) & Q.nonzero(x)) is False

    for function in (log, acos):
        assert satask(Q.algebraic(function(7))) is False
        assert satask(Q.algebraic(function(1, evaluate=False))) is True
        assert satask(Q.algebraic(function(x)), Q.algebraic(x)) is None
        assert satask(
            Q.algebraic(function(x)),
            Q.algebraic(x) & Q.nonzero(x - 1)) is False

    for function in (cot, acot):
        assert satask(Q.algebraic(function(7))) is False
        assert satask(Q.algebraic(function(x)), Q.algebraic(x)) is False


def test_factorial_and_sign_facts() -> None:
    assert satask(Q.positive(factorial(x)), Q.integer(x) & Q.positive(x)) is True
    assert satask(Q.positive(factorial(x)), Q.integer(x)) is None
    assert satask(Q.integer(factorial(x)), Q.integer(x)) is True

    assert satask(Q.finite(sign(x))) is True
    assert satask(Q.finite(sign(x)), ~Q.finite(x)) is True


def test_issue_5833_and_7246_regressions() -> None:
    assert satask(Q.positive(log(x)**2), Q.positive(x)) is None
    assert satask(~Q.negative(log(x)**2), Q.positive(x)) is True


def test_function_facts_register_local_predicate_formulas() -> None:
    expression = log(x)
    facts = class_fact_registry(expression)
    assert facts
    assert all(isinstance(fact, Formula) for fact in facts)
    for fact in facts:
        for atom in iter_atoms(fact):
            assert isinstance(atom, LocalAppliedPredicate)

    registry = ClassFactRegistry()
    register_function_facts(registry)
    assert registry(expression) == facts

    atoms = [atom for fact in facts for atom in iter_atoms(fact)]
    assert all(isinstance(atom, LocalAppliedPredicate) for atom in atoms)
    assert LocalQ.real(expression) in atoms


def test_add_facts_needed_by_functions() -> None:
    assert satask(Q.real(x + I), Q.real(x)) is False
    assert satask(Q.complex(x + y), Q.complex(x) & Q.complex(y)) is True


def test_function_facts_do_not_query_old_assumptions(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assumptions = importlib.import_module("sympy.core.assumptions")

    def fail(fact: str, obj: object) -> bool:
        raise AssertionError(f"old assumptions queried for {fact!r}")

    monkeypatch.setattr(assumptions, "_ask", fail)

    assert satask(Q.real(exp(x)), Q.real(x)) is True
    assert satask(Q.positive(atan(p)), Q.positive(p)) is True
    assert satask(Q.algebraic(exp(7))) is False
    assert satask(Q.positive(factorial(x)), Q.integer(x) & Q.positive(x)) is True
    assert satask(Q.real(sin(x)), Q.real(x)) is True
    assert satask(Q.finite(sign(oo))) is True
