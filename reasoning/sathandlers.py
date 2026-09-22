"""Facts inferred from the structure of SymPy expressions.

This module only uses SymPy to inspect expressions and create predicate atoms.
The facts themselves are lightweight formulas from :mod:`reasoning.clauses`.

Most handlers mirror the tri-state rules in SymPy's ``assumptions.handlers``
package.  :func:`_closed_group` reproduces ``test_closed_group`` (all arguments
share the predicate, or exactly one does not), while the sign and parity
handlers reproduce the corresponding ``Add``/``Mul``/``Pow`` loops.  The rules
are emitted as implications so the SAT core can combine them with the imported
known predicate facts.
"""
from __future__ import annotations

from typing import Callable

from sympy.core import Add, Mul, Number, NumberSymbol, Pow
from sympy.core.numbers import (
    ComplexInfinity, Exp1, ImaginaryUnit, NegativeOne, Rational, pi,
)
from sympy.core.singleton import S
from sympy.functions.elementary.complexes import Abs
from sympy.functions.elementary.exponential import log
from sympy.logic.boolalg import And, Or
from sympy.matrices.expressions import MatMul

from reasoning.clauses import AND, EQUIVALENT, IMPLIES, NOT, OR, XOR
from reasoning.functionfacts import register_function_facts
from reasoning.numberfacts import number_facts
from reasoning.predicates import Q
from reasoning.registry import ClassFactRegistry
from reasoning.sympy_types import SymPyExpr

PredicateCall = Callable[[SymPyExpr], object]


# The public helpers preserve their old signature. Registered handlers use the
# predicate-callable helpers below, so they never create a SymPy Boolean
# expression or substitute a placeholder into one.
def allargs(symbol: SymPyExpr, fact: SymPyExpr, expr: SymPyExpr) -> SymPyExpr:
    return And(*(fact.subs(symbol, arg) for arg in expr.args))


def anyarg(symbol: SymPyExpr, fact: SymPyExpr, expr: SymPyExpr) -> SymPyExpr:
    return Or(*(fact.subs(symbol, arg) for arg in expr.args))


def exactlyonearg(symbol: SymPyExpr, fact: SymPyExpr, expr: SymPyExpr) -> SymPyExpr:
    predicates = [fact.subs(symbol, arg) for arg in expr.args]
    return Or(*(And(predicate, *(~other for other in predicates[:index] + predicates[index + 1:]))
                for index, predicate in enumerate(predicates)))


def _allargs(predicate: PredicateCall, expr: SymPyExpr) -> object:
    return AND(*(predicate(arg) for arg in expr.args))


def _anyarg(predicate: PredicateCall, expr: SymPyExpr) -> object:
    return OR(*(predicate(arg) for arg in expr.args))


def _exactlyonearg(predicate: PredicateCall, expr: SymPyExpr) -> object:
    predicates = [predicate(arg) for arg in expr.args]
    return OR(*(AND(item, *(NOT(other) for other in predicates[:index] + predicates[index + 1:]))
                for index, item in enumerate(predicates)))


def _closed_group(predicate: PredicateCall, expr: SymPyExpr) -> list[object]:
    """The two facts of SymPy's fuzzy ``test_closed_group`` rule.

    All arguments sharing the predicate makes it hold for the expression; a
    single argument that lacks it (with every other argument sharing it) makes
    it fail.  More than one exception stays unknown.
    """
    return [
        IMPLIES(_allargs(predicate, expr), predicate(expr)),
        IMPLIES(_exactlyonearg(lambda arg: NOT(predicate(arg)), expr),
                NOT(predicate(expr))),
    ]


def _mul_closed_group(predicate: PredicateCall, expr: SymPyExpr) -> list[object]:
    """Like :func:`_closed_group` but guarded by nonzero factors.

    A zero factor makes the product zero (and hence rational, algebraic, and
    so on), so the single-exception direction only applies when every factor
    is known to be nonzero.
    """
    return [
        IMPLIES(_allargs(predicate, expr), predicate(expr)),
        IMPLIES(
            AND(_allargs(lambda arg: NOT(Q.zero(arg)), expr),
                _exactlyonearg(lambda arg: NOT(predicate(arg)), expr)),
            NOT(predicate(expr)),
        ),
    ]


class_fact_registry = ClassFactRegistry()


@class_fact_registry.multiregister(Abs)
def _abs_facts(expr: SymPyExpr) -> list[object]:
    arg = expr.args[0]
    return [
        Q.nonnegative(expr),
        EQUIVALENT(NOT(Q.zero(arg)), NOT(Q.zero(expr))),
        IMPLIES(Q.even(arg), Q.even(expr)),
        IMPLIES(Q.odd(arg), Q.odd(expr)),
        IMPLIES(Q.integer(arg), Q.integer(expr)),
    ]


_ADD_CLOSURE_PREDICATES = (
    Q.real, Q.complex, Q.extended_real, Q.rational, Q.integer,
    Q.algebraic, Q.hermitian, Q.antihermitian,
)


@class_fact_registry.multiregister(Add)
def _add_closure_facts(expr: SymPyExpr) -> list[object]:
    return [
        fact
        for predicate in _ADD_CLOSURE_PREDICATES
        for fact in _closed_group(predicate, expr)
    ]


@class_fact_registry.register(Add)
def _add_irrational_fact(expr: SymPyExpr) -> object:
    return IMPLIES(
        AND(_allargs(Q.real, expr), _exactlyonearg(Q.irrational, expr)),
        Q.irrational(expr),
    )


@class_fact_registry.register(Add)
def _add_sign_facts(expr: SymPyExpr) -> object:
    return AND(
        IMPLIES(
            AND(Q.real(expr),
                _allargs(lambda arg: OR(Q.positive(arg), NOT(Q.negative(arg))), expr),
                _anyarg(Q.positive, expr)),
            Q.positive(expr)),
        IMPLIES(
            AND(Q.real(expr),
                _allargs(lambda arg: OR(Q.negative(arg), NOT(Q.positive(arg))), expr),
                _anyarg(Q.negative, expr)),
            Q.negative(expr)),
    )


@class_fact_registry.register(Add)
def _add_parity_facts(expr: SymPyExpr) -> object:
    odd = [Q.odd(arg) for arg in expr.args]
    return AND(
        IMPLIES(_allargs(Q.integer, expr), EQUIVALENT(Q.odd(expr), XOR(*odd))),
        IMPLIES(_allargs(Q.integer, expr), EQUIVALENT(Q.even(expr), NOT(XOR(*odd)))),
    )


@class_fact_registry.register(Add)
def _add_imaginary_facts(expr: SymPyExpr) -> object:
    imaginary_or_real = _allargs(
        lambda arg: OR(Q.imaginary(arg), Q.real(arg)), expr)
    return AND(
        IMPLIES(_allargs(Q.imaginary, expr), Q.imaginary(expr)),
        IMPLIES(AND(imaginary_or_real, _exactlyonearg(Q.real, expr)),
                NOT(Q.imaginary(expr))),
    )


@class_fact_registry.register(Add)
def _add_nonzero_fact(expr: SymPyExpr) -> object:
    return IMPLIES(
        OR(_allargs(Q.positive, expr), _allargs(Q.negative, expr)),
        Q.nonzero(expr),
    )


@class_fact_registry.register(Add)
def _add_commutative_facts(expr: SymPyExpr) -> object:
    return AND(
        IMPLIES(_allargs(Q.commutative, expr), Q.commutative(expr)),
        IMPLIES(_anyarg(lambda arg: NOT(Q.commutative(arg)), expr),
                NOT(Q.commutative(expr))),
    )


@class_fact_registry.register(Add)
def _add_infinite_fact(expr: SymPyExpr) -> object:
    return IMPLIES(
        AND(_exactlyonearg(Q.infinite, expr),
            _allargs(lambda arg: OR(Q.finite(arg), Q.infinite(arg)), expr)),
        Q.infinite(expr),
    )


_MUL_CLOSURE_PREDICATES = (Q.complex, Q.rational, Q.algebraic)


@class_fact_registry.multiregister(Mul)
def _mul_closure_facts(expr: SymPyExpr) -> list[object]:
    return [
        fact
        for predicate in _MUL_CLOSURE_PREDICATES
        for fact in _mul_closed_group(predicate, expr)
    ]


@class_fact_registry.register(Mul)
def _mul_facts(expr: SymPyExpr) -> object:
    return AND(
        EQUIVALENT(Q.zero(expr), _anyarg(Q.zero, expr)),
        IMPLIES(_allargs(Q.integer, expr), Q.integer(expr)),
        IMPLIES(
            AND(_allargs(lambda arg: NOT(Q.zero(arg)), expr),
                _exactlyonearg(lambda arg: NOT(Q.rational(arg)), expr)),
            NOT(Q.integer(expr)),
        ),
        IMPLIES(_allargs(Q.nonzero, expr), Q.nonzero(expr)),
    )


@class_fact_registry.register(Mul)
def _mul_commutative_facts(expr: SymPyExpr) -> object:
    return AND(
        IMPLIES(_allargs(Q.commutative, expr), Q.commutative(expr)),
        IMPLIES(_anyarg(lambda arg: NOT(Q.commutative(arg)), expr),
                NOT(Q.commutative(expr))),
    )


@class_fact_registry.register(Mul)
def _mul_real_facts(expr: SymPyExpr) -> object:
    real_or_imaginary = _allargs(
        lambda arg: OR(Q.real(arg), Q.imaginary(arg)), expr)
    imaginary = [Q.imaginary(arg) for arg in expr.args]
    odd = XOR(*imaginary)
    return AND(
        IMPLIES(AND(real_or_imaginary, NOT(odd)), Q.real(expr)),
        IMPLIES(AND(real_or_imaginary, odd),
                EQUIVALENT(Q.real(expr), Q.zero(expr))),
        IMPLIES(AND(real_or_imaginary, NOT(odd)), NOT(Q.imaginary(expr))),
        IMPLIES(AND(real_or_imaginary, odd, NOT(Q.zero(expr))),
                Q.imaginary(expr)),
    )


@class_fact_registry.register(Mul)
def _mul_sign_facts(expr: SymPyExpr) -> object:
    sign_known = _allargs(
        lambda arg: OR(Q.positive(arg), Q.negative(arg)), expr)
    odd = XOR(*(Q.negative(arg) for arg in expr.args))
    return AND(
        IMPLIES(sign_known, EQUIVALENT(Q.negative(expr), odd)),
        IMPLIES(sign_known, EQUIVALENT(Q.positive(expr), NOT(odd))),
    )


@class_fact_registry.register(Mul)
def _mul_hermitian_facts(expr: SymPyExpr) -> object:
    hermitian_or_anti = _allargs(
        lambda arg: OR(Q.hermitian(arg), Q.antihermitian(arg)), expr)
    all_hermitian = _allargs(Q.hermitian, expr)
    all_antihermitian = _allargs(Q.antihermitian, expr)
    one_antihermitian = _exactlyonearg(Q.antihermitian, expr)
    facts = [
        IMPLIES(all_hermitian, Q.hermitian(expr)),
        IMPLIES(all_hermitian, NOT(Q.antihermitian(expr))),
        IMPLIES(AND(hermitian_or_anti, one_antihermitian), NOT(Q.hermitian(expr))),
        IMPLIES(AND(hermitian_or_anti, one_antihermitian), Q.antihermitian(expr)),
    ]
    if len(expr.args) % 2 == 0:
        facts.append(IMPLIES(all_antihermitian, Q.hermitian(expr)))
        facts.append(IMPLIES(all_antihermitian, NOT(Q.antihermitian(expr))))
    else:
        facts.append(IMPLIES(all_antihermitian, NOT(Q.hermitian(expr))))
        facts.append(IMPLIES(all_antihermitian, Q.antihermitian(expr)))
    return AND(*facts)


@class_fact_registry.register(Mul)
def _mul_parity_facts(expr: SymPyExpr) -> object:
    integer = _allargs(Q.integer, expr)
    all_odd = _allargs(Q.odd, expr)
    facts = [
        IMPLIES(AND(integer, _anyarg(Q.even, expr)), Q.even(expr)),
        IMPLIES(AND(integer, _allargs(lambda arg: NOT(Q.even(arg)), expr), all_odd),
                NOT(Q.even(expr))),
    ]
    previous: SymPyExpr | None = None
    for arg in expr.args:
        if previous is not None:
            facts.append(IMPLIES(AND(integer, Q.odd(previous + arg)), Q.even(expr)))
        previous = arg
    return AND(*facts)


@class_fact_registry.register(Mul)
def _mul_prime_fact(expr: SymPyExpr) -> object:
    return IMPLIES(_allargs(Q.prime, expr), NOT(Q.prime(expr)))


@class_fact_registry.register(Mul)
def _mul_irrational_fact(expr: SymPyExpr) -> object:
    return IMPLIES(
        AND(_allargs(Q.real, expr), _allargs(lambda arg: NOT(Q.zero(arg)), expr)),
        IMPLIES(_exactlyonearg(Q.irrational, expr), Q.irrational(expr)),
    )


@class_fact_registry.register(Mul)
def _mul_infinite_fact(expr: SymPyExpr) -> object:
    return IMPLIES(
        AND(_anyarg(Q.infinite, expr),
            _allargs(lambda arg: OR(Q.finite(arg), Q.infinite(arg)), expr),
            _allargs(lambda arg: NOT(Q.zero(arg)), expr)),
        Q.infinite(expr),
    )


@class_fact_registry.register(MatMul)
def _matmul_invertible_fact(expr: SymPyExpr) -> object:
    return IMPLIES(
        _allargs(Q.square, expr),
        EQUIVALENT(Q.invertible(expr), _allargs(Q.invertible, expr)),
    )


@class_fact_registry.multiregister(Pow)
def _pow_facts(expr: SymPyExpr) -> list[object]:
    base, exp = expr.base, expr.exp
    return [
        IMPLIES(AND(Q.real(base), Q.even(exp), Q.nonnegative(exp)), Q.nonnegative(expr)),
        IMPLIES(AND(Q.nonnegative(base), Q.odd(exp), Q.nonnegative(exp)), Q.nonnegative(expr)),
        IMPLIES(AND(Q.nonpositive(base), Q.odd(exp), Q.nonnegative(exp)), Q.nonpositive(expr)),
        EQUIVALENT(Q.zero(expr), AND(Q.zero(base), Q.positive(exp))),
    ]


@class_fact_registry.register(Pow)
def _pow_commutative_facts(expr: SymPyExpr) -> object:
    return AND(
        IMPLIES(_allargs(Q.commutative, expr), Q.commutative(expr)),
        IMPLIES(_anyarg(lambda arg: NOT(Q.commutative(arg)), expr),
                NOT(Q.commutative(expr))),
    )


@class_fact_registry.register(Pow)
def _pow_closure_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    defined = OR(NOT(Q.zero(base)), NOT(Q.negative(exp)))
    real_power = OR(Q.integer(exp), AND(Q.real(exp), Q.nonnegative(base)))
    return AND(
        IMPLIES(_allargs(Q.complex, expr), Q.complex(expr)),
        IMPLIES(_exactlyonearg(lambda arg: NOT(Q.complex(arg)), expr),
                NOT(Q.complex(expr))),
        IMPLIES(AND(_allargs(Q.extended_real, expr), defined, real_power),
                Q.extended_real(expr)),
    )


@class_fact_registry.register(Pow)
def _pow_real_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    facts = [
        IMPLIES(AND(Q.imaginary(base), Q.integer(exp)),
                EQUIVALENT(Q.real(expr), Q.even(exp))),
        IMPLIES(Q.imaginary(exp),
                EQUIVALENT(Q.real(expr), Q.imaginary(log(base)))),
        IMPLIES(AND(Q.real(base), Q.real(exp), Q.positive(base)), Q.real(expr)),
        IMPLIES(
            AND(Q.real(base), Q.real(exp), OR(Q.zero(base), Q.integer(exp)),
                OR(NOT(Q.zero(base)), NOT(Q.negative(exp)))),
            Q.real(expr)),
    ]
    if isinstance(exp, Rational) and exp.q % 2 == 0:
        facts.append(IMPLIES(
            AND(Q.real(base), Q.real(exp)),
            EQUIVALENT(Q.real(expr), Q.nonnegative(base))))
    if isinstance(base, Exp1):
        facts.append(IMPLIES(
            OR(Q.integer(exp / S.ImaginaryUnit / pi), Q.real(exp)),
            Q.real(expr)))
    return AND(*facts)


@class_fact_registry.register(Pow)
def _pow_sign_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    return AND(
        IMPLIES(AND(Q.real(base), Q.positive(base), Q.real(exp)),
                NOT(Q.negative(expr))),
        IMPLIES(AND(Q.real(base), Q.even(exp),
                    OR(NOT(Q.zero(base)), Q.positive(exp))),
                NOT(Q.negative(expr))),
        IMPLIES(AND(Q.real(base), Q.odd(exp)),
                EQUIVALENT(Q.negative(expr), Q.negative(base))),
        IMPLIES(AND(Q.even(exp), Q.real(base), Q.nonzero(base),
                    NOT(Q.negative(exp))),
                Q.positive(expr)),
        IMPLIES(AND(Q.even(exp), Q.real(base), Q.zero(base), Q.positive(exp)),
                NOT(Q.positive(expr))),
        IMPLIES(AND(Q.positive(base), Q.real(exp)), Q.positive(expr)),
        IMPLIES(AND(Q.negative(base), Q.odd(exp)), NOT(Q.positive(expr))),
    )


@class_fact_registry.register(Pow)
def _pow_rational_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    facts = [
        IMPLIES(AND(Q.integer(exp), Q.rational(base), NOT(Q.zero(base))),
                Q.rational(expr)),
        IMPLIES(AND(Q.integer(exp), Q.rational(base), Q.zero(base), Q.positive(exp)),
                Q.rational(expr)),
        IMPLIES(AND(Q.rational(exp), Q.zero(base), Q.positive(exp)),
                Q.rational(expr)),
        IMPLIES(AND(Q.rational(exp), Q.eq(base, S.One)), Q.rational(expr)),
        IMPLIES(AND(Q.rational(exp), Q.prime(base), NOT(Q.integer(exp))),
                NOT(Q.rational(expr))),
        IMPLIES(AND(Q.integer(exp), NOT(Q.algebraic(base))),
                EQUIVALENT(Q.rational(expr), Q.zero(exp))),
    ]
    if isinstance(exp, NegativeOne):
        facts.append(IMPLIES(Q.irrational(base), NOT(Q.rational(expr))))
    if isinstance(base, Exp1):
        facts.append(IMPLIES(Q.rational(exp),
                             EQUIVALENT(Q.rational(expr), Q.zero(exp))))
    return AND(*facts)


@class_fact_registry.register(Pow)
def _pow_integer_fact(expr: SymPyExpr) -> object:
    return IMPLIES(
        AND(Q.integer(expr.base), Q.integer(expr.exp), NOT(Q.negative(expr.exp))),
        Q.integer(expr),
    )


@class_fact_registry.register(Pow)
def _pow_parity_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    facts = [
        IMPLIES(AND(Q.integer(exp), Q.positive(exp)),
                EQUIVALENT(Q.even(expr), Q.even(base))),
        IMPLIES(AND(Q.integer(exp), NOT(Q.negative(exp)), Q.odd(base)),
                NOT(Q.even(expr))),
    ]
    if isinstance(base, NegativeOne):
        facts.append(IMPLIES(Q.integer(exp), Q.odd(expr)))
    return AND(*facts)


@class_fact_registry.register(Pow)
def _pow_imaginary_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    return AND(
        IMPLIES(AND(Q.imaginary(base), Q.integer(exp), Q.odd(exp)),
                Q.imaginary(expr)),
        IMPLIES(AND(Q.imaginary(base), Q.integer(exp), Q.even(exp)),
                NOT(Q.imaginary(expr))),
        IMPLIES(AND(Q.imaginary(exp), Q.imaginary(log(base))),
                NOT(Q.imaginary(expr))),
        IMPLIES(AND(Q.real(base), Q.real(exp), Q.positive(base)),
                NOT(Q.imaginary(expr))),
        IMPLIES(AND(Q.real(base), Q.real(exp), NOT(Q.rational(exp))),
                NOT(Q.imaginary(expr))),
        IMPLIES(AND(Q.real(base), Q.real(exp), Q.integer(exp)),
                NOT(Q.imaginary(expr))),
        IMPLIES(AND(Q.real(base), Q.real(exp), Q.rational(exp),
                    NOT(Q.integer(exp)), NOT(Q.integer(2 * exp))),
                NOT(Q.imaginary(expr))),
        IMPLIES(AND(Q.real(base), Q.real(exp), Q.integer(2 * exp),
                    NOT(Q.integer(exp)), Q.negative(base)),
                Q.imaginary(expr)),
        IMPLIES(AND(Q.real(base), Q.real(exp), Q.integer(2 * exp),
                    NOT(Q.integer(exp)), NOT(Q.negative(base))),
                NOT(Q.imaginary(expr))),
    )


@class_fact_registry.register(Pow)
def _pow_algebraic_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    facts = [
        IMPLIES(AND(Q.algebraic(base), Q.rational(exp)), Q.algebraic(expr)),
        IMPLIES(AND(NOT(Q.algebraic(base)), Q.integer(exp), Q.positive(exp)),
                NOT(Q.algebraic(expr))),
    ]
    if isinstance(base, Exp1):
        facts.append(IMPLIES(AND(Q.algebraic(exp)),
                             EQUIVALENT(Q.algebraic(expr), Q.zero(exp))))
    return AND(*facts)


@class_fact_registry.register(Pow)
def _pow_finite_fact(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    return IMPLIES(
        AND(Q.finite(base), Q.finite(exp),
            OR(NOT(Q.zero(base)), NOT(Q.negative(exp)))),
        Q.finite(expr),
    )


@class_fact_registry.register(Pow)
def _pow_nonzero_fact(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    return IMPLIES(
        AND(OR(Q.nonzero(base), Q.zero(exp)), Q.real(expr)),
        Q.nonzero(expr),
    )


@class_fact_registry.register(Pow)
def _pow_hermitian_fact(expr: SymPyExpr) -> object:
    return IMPLIES(AND(Q.hermitian(expr.base), Q.integer(expr.exp)),
                   Q.hermitian(expr))


@class_fact_registry.register(Pow)
def _pow_antihermitian_facts(expr: SymPyExpr) -> object:
    base, exp = expr.base, expr.exp
    return AND(
        IMPLIES(AND(Q.hermitian(base), Q.integer(exp)),
                NOT(Q.antihermitian(expr))),
        IMPLIES(AND(Q.antihermitian(base), Q.even(exp)),
                NOT(Q.antihermitian(expr))),
        IMPLIES(AND(Q.antihermitian(base), Q.odd(exp)),
                Q.antihermitian(expr)),
    )


class_fact_registry.multiregister(
    Number, NumberSymbol, ImaginaryUnit, ComplexInfinity)(number_facts)

register_function_facts(class_fact_registry)


__all__ = [
    'ClassFactRegistry', 'allargs', 'anyarg', 'exactlyonearg',
    'class_fact_registry',
]
