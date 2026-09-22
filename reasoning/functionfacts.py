"""Facts about elementary functions from direct structural inspection.

This module extends :mod:`reasoning.numberfacts` from numbers to the standard
elementary functions.  Like that module it never reads SymPy's old
assumptions: the class of an expression selects a rule table, and every rule is
a lightweight formula over predicate applications whose single argument is a
SymPy expression the discovery loop can visit.

Several rules mention expressions built from the argument, such as ``arg - 1``
or ``arg/(I*pi)``.  That is deliberate: the SAT layer can only relate predicates
applied to the same expression, so structural side conditions have to be spelled
out as well-known objects (``Q.positive(x - 1)`` and the like).  The discovery
loop then treats those expressions as new subjects and derives their numeric
facts.

The generic ``Add`` rules at the bottom are the only facts here that are not
function specific.  They are the smallest structural facts the function rules
need in order to talk about sums such as ``log(1 + I)``; they are sound on their
own and overlap with the dedicated Add/Mul/Pow facts kept elsewhere.
"""
from __future__ import annotations

from typing import Callable

from sympy.core.add import Add
from sympy.core.numbers import Exp1
from sympy.core.power import Pow
from sympy.core.singleton import S
from sympy.functions.combinatorial.factorials import factorial
from sympy.functions.elementary.complexes import Abs, im, re, sign
from sympy.functions.elementary.exponential import exp, log
from sympy.functions.elementary.trigonometric import (
    acos, acot, asin, atan, cos, cot, sin, tan,
)

from reasoning.clauses import AND, EQUIVALENT, IMPLIES, NOT, OR
from reasoning.predicates import Q
from reasoning.registry import ClassFactRegistry
from reasoning.sympy_types import SymPyExpr

PredicateCall = Callable[[SymPyExpr], object]

_IMAGINARY_PI = S.ImaginaryUnit * S.Pi


def _argument(expr: SymPyExpr) -> SymPyExpr:
    return expr.args[0]


def _allargs(predicate: PredicateCall, expr: SymPyExpr) -> object:
    return AND(*(predicate(arg) for arg in expr.args))


def _exactlyonearg(predicate: PredicateCall, expr: SymPyExpr) -> object:
    predicates = [predicate(arg) for arg in expr.args]
    return OR(*(AND(item, *(NOT(other) for other in predicates[:index] + predicates[index + 1:]))
                for index, item in enumerate(predicates)))


def _sin_cos_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(Q.real(arg), Q.real(expr)),
        Q.complex(expr),
        Q.finite(expr),
    ]


def _zero_algebraic_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(Q.zero(arg), Q.algebraic(expr)),
        IMPLIES(AND(Q.algebraic(arg), Q.nonzero(arg)), NOT(Q.algebraic(expr))),
    ]


def _atan_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(Q.real(arg), Q.real(expr)),
        EQUIVALENT(Q.positive(expr), Q.positive(arg)),
    ]


def _asin_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(AND(Q.positive(arg), Q.nonpositive(arg - 1)), Q.positive(expr)),
        IMPLIES(AND(Q.negative(arg), Q.nonnegative(arg + 1)), NOT(Q.positive(expr))),
    ]


def _acos_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(
            AND(Q.nonnegative(arg + 1), Q.nonpositive(arg - 1)),
            Q.positive(expr),
        ),
        IMPLIES(Q.zero(arg - 1), Q.algebraic(expr)),
        IMPLIES(AND(Q.algebraic(arg), Q.nonzero(arg - 1)), NOT(Q.algebraic(expr))),
    ]


def _acot_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(Q.real(arg), Q.real(expr)),
        EQUIVALENT(Q.positive(expr), Q.real(arg)),
        IMPLIES(Q.algebraic(arg), NOT(Q.algebraic(expr))),
    ]


def _cot_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [IMPLIES(Q.algebraic(arg), NOT(Q.algebraic(expr)))]


def _exp_facts(expr: SymPyExpr) -> list[object]:
    if isinstance(expr, Pow) and not isinstance(expr.base, Exp1):
        return []
    arg = expr.exp
    # ``period`` is the multiple of ``I*pi`` in the exponent, so that
    # ``exp(2*pi*I)`` has period 2 and ``exp(pi*I/2)`` has period 1/2.
    period = arg / _IMAGINARY_PI
    twice = 2 * period
    return [
        IMPLIES(OR(Q.real(arg), Q.integer(period)), Q.real(expr)),
        IMPLIES(AND(Q.imaginary(arg), NOT(Q.integer(period))), NOT(Q.real(expr))),
        IMPLIES(Q.real(arg), Q.positive(expr)),
        IMPLIES(Q.even(period), Q.positive(expr)),
        IMPLIES(Q.odd(period), Q.negative(expr)),
        IMPLIES(AND(Q.integer(twice), NOT(Q.integer(period))), Q.imaginary(expr)),
        IMPLIES(Q.finite(arg), Q.finite(expr)),
        IMPLIES(Q.zero(arg), Q.algebraic(expr)),
        IMPLIES(AND(Q.algebraic(arg), Q.nonzero(arg)), NOT(Q.algebraic(expr))),
    ]


def _log_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(Q.positive(arg), Q.real(expr)),
        IMPLIES(Q.positive(arg - 1), Q.positive(expr)),
        IMPLIES(Q.positive(arg), NOT(Q.imaginary(expr))),
        IMPLIES(Q.imaginary(arg), NOT(Q.real(expr))),
        IMPLIES(AND(Q.complex(arg), NOT(Q.real(arg))), NOT(Q.real(expr))),
        IMPLIES(AND(Q.real(arg), NOT(Q.positive(arg))), NOT(Q.real(expr))),
        IMPLIES(AND(Q.finite(arg), NOT(Q.zero(arg))), Q.finite(expr)),
        IMPLIES(Q.zero(arg), NOT(Q.finite(expr))),
        IMPLIES(Q.infinite(arg), NOT(Q.finite(expr))),
        IMPLIES(Q.zero(arg - 1), Q.algebraic(expr)),
        IMPLIES(AND(Q.algebraic(arg), Q.nonzero(arg - 1)), NOT(Q.algebraic(expr))),
    ]


def _abs_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        Q.complex(expr),
        IMPLIES(Q.nonzero(arg), Q.positive(expr)),
        IMPLIES(Q.nonzero(arg), Q.nonzero(expr)),
    ]


def _re_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        Q.real(expr),
        Q.complex(expr),
        IMPLIES(Q.even(arg), Q.even(expr)),
    ]


def _im_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        Q.real(expr),
        Q.complex(expr),
        IMPLIES(Q.even(arg), Q.even(expr)),
        IMPLIES(Q.real(arg), Q.even(expr)),
    ]


def _factorial_facts(expr: SymPyExpr) -> list[object]:
    arg = _argument(expr)
    return [
        IMPLIES(AND(Q.integer(arg), Q.positive(arg)), Q.positive(expr)),
        IMPLIES(Q.integer(arg), Q.integer(expr)),
    ]


def _sign_facts(expr: SymPyExpr) -> list[object]:
    return [Q.finite(expr)]


def _add_complex_facts(expr: SymPyExpr) -> list[object]:
    return [IMPLIES(_allargs(Q.complex, expr), Q.complex(expr))]


def _add_not_real_facts(expr: SymPyExpr) -> list[object]:
    return [IMPLIES(
        _exactlyonearg(lambda arg: NOT(Q.real(arg)), expr), NOT(Q.real(expr)))]


def register_function_facts(registry: ClassFactRegistry) -> None:
    """Attach the elementary-function handlers to a fact registry."""
    registry.multiregister(sin, cos)(_sin_cos_facts)
    registry.multiregister(sin, tan, asin, atan, cos)(_zero_algebraic_facts)
    registry.multiregister(exp)(_exp_facts)
    registry.multiregister(Pow)(_exp_facts)
    registry.multiregister(atan)(_atan_facts)
    registry.multiregister(asin)(_asin_facts)
    registry.multiregister(acos)(_acos_facts)
    registry.multiregister(acot)(_acot_facts)
    registry.multiregister(cot)(_cot_facts)
    registry.multiregister(log)(_log_facts)
    registry.multiregister(Abs)(_abs_facts)
    registry.multiregister(re)(_re_facts)
    registry.multiregister(im)(_im_facts)
    registry.multiregister(factorial)(_factorial_facts)
    registry.multiregister(sign)(_sign_facts)
    registry.multiregister(Add)(_add_complex_facts)
    registry.multiregister(Add)(_add_not_real_facts)


__all__ = ["register_function_facts"]
