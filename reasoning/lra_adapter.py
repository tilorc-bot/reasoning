"""Interpret local relation atoms as linear-arithmetic constraints.

:mod:`reasoning.lra` knows nothing about SymPy; this adapter is the boundary
that turns the applied predicates in a :class:`~reasoning.clauses.ClauseDB`
into its ``(terms, constant, strict, equality)`` records.  Terms stay SymPy
expressions, but they are opaque keys to the solver: only the rational
coefficients and constants are interpreted.

Only ``Q.eq``, ``Q.gt``, ``Q.lt``, ``Q.ge`` and ``Q.le`` atoms with exactly two
arguments are interpreted.  Everything else -- predicates, ``Q.ne``, atoms
with non-rational parameters, nan, imaginary and infinite arguments, and
relations the rational normalization cannot evaluate -- is left to the SAT
layer.  Skipping an atom is sound: the theory then simply cannot say anything
about it.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

from sympy import S
from sympy.core.add import Add
from sympy.core.mul import Mul
from sympy.core.relational import Eq, Ge, Gt, Le, Lt

from .clauses import ClauseDB
from .lra import LRAConstraint, LRASolver
from .predicates import AppliedPredicate

_RELATIONS: dict[str, Any] = {
    "eq": Eq, "gt": Gt, "lt": Lt, "ge": Ge, "le": Le,
}


class UnhandledLRA(Exception):
    """Raised for an atom that cannot be interpreted as a linear constraint."""


def _split_constant(expr: Any, operation: Any) -> tuple[Any, Any]:
    """Return the symbol-dependent and symbol-free parts of *expr*.

    ``operation`` is :class:`~sympy.core.add.Add` or
    :class:`~sympy.core.mul.Mul`, selecting additive terms or multiplicative
    factors respectively.
    """
    constant_args = [arg for arg in operation.make_args(expr)
                     if not arg.free_symbols]
    variable_args = [arg for arg in operation.make_args(expr)
                     if arg.free_symbols]
    return operation(*variable_args), operation(*constant_args)


def _fraction(value: Any) -> Fraction:
    if value.is_Rational is not True:
        raise UnhandledLRA(f"{value} is not rational")
    return Fraction(int(value.p), int(value.q))


def _interpret(name: str, lhs: Any, rhs: Any) -> bool | LRAConstraint:
    """Interpret one relation atom.

    Returns ``True``/``False`` for a constant relation, otherwise the
    constraint record for the solver.  Raises :class:`UnhandledLRA` when the
    relation is outside the supported fragment.
    """
    if lhs is S.NaN or rhs is S.NaN:
        raise UnhandledLRA("relation contains nan")
    if lhs.is_Matrix is True or rhs.is_Matrix is True:
        # MatrixExpr is an Expr, but its arithmetic is not scalar; for
        # example Eq(A - A, 0) is False for a zero matrix, which would turn
        # the true relation Q.eq(A, A) into a false one.
        raise UnhandledLRA("relation contains a matrix")
    if getattr(lhs, "is_imaginary", None) is True or getattr(
            rhs, "is_imaginary", None) is True:
        raise UnhandledLRA("relation contains an imaginary component")
    if lhs in (S.Infinity, S.NegativeInfinity) or rhs in (S.Infinity,
                                                          S.NegativeInfinity):
        raise UnhandledLRA("relation contains infinity")

    try:
        expr = lhs - rhs
    except (TypeError, ValueError) as error:
        raise UnhandledLRA(f"{name}({lhs}, {rhs}) is not subtractable: {error}")
    relation = _RELATIONS[name](expr, S.Zero)
    if relation is S.true:
        return True
    if relation is S.false:
        return False
    if not expr.free_symbols:
        raise UnhandledLRA(f"{name}({lhs}, {rhs}) could not be evaluated")

    # Normalize >= and > to <= and < by negating the expression.
    if name in ("ge", "gt"):
        expr = -expr

    variable_part, constant = _split_constant(expr, Add)
    split_terms = [_split_constant(term, Mul)
                   for term in Add.make_args(variable_part)]
    if not split_terms:
        raise UnhandledLRA("relation has no variable part")

    terms: list[tuple[Any, Fraction]] = []
    for term, coefficient in split_terms:
        if not term.free_symbols:
            raise UnhandledLRA(f"{term} is not a variable term")
        terms.append((term, _fraction(coefficient)))

    strict = name in ("gt", "lt")
    equality = name == "eq"
    return tuple(terms), _fraction(constant), strict, equality


def lra_constraints(db: ClauseDB) -> tuple[
        dict[int, LRAConstraint], list[list[int]]]:
    """Collect LRA constraints and unit conflicts from a clause database.

    The conflict clauses force constant relations to the truth value SymPy
    computed for them.  Atoms that cannot be interpreted are skipped.
    """
    constraints: dict[int, LRAConstraint] = {}
    conflicts: list[list[int]] = []
    for variable, atom in db.symbols.items():
        if not isinstance(atom, AppliedPredicate):
            continue
        if atom.name not in _RELATIONS or len(atom.arguments) != 2:
            continue
        try:
            interpreted = _interpret(atom.name, *atom.arguments)
        except UnhandledLRA:
            continue
        if interpreted is True:
            conflicts.append([variable])
        elif interpreted is False:
            conflicts.append([-variable])
        else:
            constraints[variable] = interpreted
    return constraints, conflicts


def build_lra_theory(db: ClauseDB, testing_mode: bool = False) -> tuple[
        LRASolver | None, list[list[int]]]:
    """Return an LRA solver for *db* and its immediate conflict clauses."""
    constraints, conflicts = lra_constraints(db)
    if not constraints:
        return None, conflicts
    return LRASolver.from_constraints(constraints, testing_mode), conflicts


__all__ = ["UnhandledLRA", "build_lra_theory", "lra_constraints"]
