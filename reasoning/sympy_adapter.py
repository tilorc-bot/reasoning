"""The boundary between SymPy expressions and the propositional core."""
from functools import lru_cache
from typing import Any, Callable, Iterable, TypeAlias, cast

from sympy import S, Symbol
from sympy.assumptions.assume import AppliedPredicate
from sympy.core.function import Function
from sympy.assumptions.ask_generated import (
    get_all_known_matrix_facts, get_all_known_number_facts,
)
from sympy.core.kind import NumberKind, UndefinedKind
from sympy.core.relational import Eq, Ne, Gt, Lt, Ge, Le
from sympy.logic.boolalg import (
    And, Or, Not, Implies, Equivalent, Xor, Xnor, ITE, Nand, Nor,
)
from sympy.matrices.kind import MatrixKind

from .clauses import (
    ClauseDB, Formula, AND, OR, NOT, IMPLIES, EQUIVALENT, XOR, ITE as IF,
    assert_formula, iter_atoms,
)
from .predicates import AppliedPredicate as LocalAppliedPredicate
from .predicates import Predicate as LocalPredicate
from .predicates import Q as LocalQ
from .sathandlers import class_fact_registry
from .sympy_types import SymPyExpr

NormalizedFormula: TypeAlias = bool | Formula | LocalAppliedPredicate


def to_sympy(value: object) -> SymPyExpr:
    """Normalize a public input to a SymPy expression.

    Python Booleans become ``S.true``/``S.false`` and legacy CNF objects are
    converted clause by clause.  Anything else must already be a SymPy
    expression, otherwise a ``TypeError`` is raised.
    """
    if isinstance(value, SymPyExpr):
        result: object = value
    elif value is True or value is False:
        result = S.true if value else S.false
    else:
        clauses = getattr(value, 'clauses', None)
        if clauses is None:
            raise TypeError(
                f"expected a SymPy expression, got {type(value).__name__}")
        result = And(*(Or(*(Not(lit.lit) if lit.is_Not else lit.lit
                            for lit in clause))
                       for clause in clauses))
    assert isinstance(result, SymPyExpr)
    return result


def to_local_predicate(applied: Any) -> LocalAppliedPredicate:
    """Convert a SymPy applied predicate to the local predicate vocabulary."""
    return LocalQ.of(applied.function.name)(*applied.arguments)


def normalize(value: object) -> NormalizedFormula:
    """Normalize a public input to a SymPy-free formula.

    SymPy Booleans, relations, and ``Q`` applications become lightweight
    formulas whose atoms are :mod:`reasoning.predicates` applications; the
    only SymPy values that remain are the expression arguments of those
    applications.  Any other leaf raises TypeError.
    """
    expr = to_sympy(value)
    assert isinstance(expr, SymPyExpr)
    formula = to_formula(expr)
    for atom in iter_atoms(formula):
        if not isinstance(atom, LocalAppliedPredicate):
            raise TypeError(f"{atom!r} is not an applied predicate")
    return cast("NormalizedFormula", formula)


def to_formula(expr: object) -> object:
    if isinstance(expr, (Formula, bool)):
        return expr
    if expr is S.true:
        return True
    if expr is S.false:
        return False
    value = cast("Any", expr)
    # Accept old CNF inputs at the helper API boundary, without using their
    # implementation anywhere in the reasoning pipeline.
    clauses = getattr(value, 'clauses', None)
    if clauses is not None:
        return AND(*(OR(*(NOT(to_formula(lit.lit)) if lit.is_Not
                           else to_formula(lit.lit) for lit in clause))
                     for clause in clauses))
    relation = {Eq: LocalQ.eq, Ne: LocalQ.ne, Gt: LocalQ.gt,
                Lt: LocalQ.lt, Ge: LocalQ.ge, Le: LocalQ.le}.get(type(value))
    if relation is not None:
        return relation(*value.args)
    operators: dict[Any, Callable[..., object]] = {
        And: AND, Or: OR, Not: NOT, Implies: IMPLIES,
        Equivalent: EQUIVALENT, Xor: XOR, ITE: IF,
    }
    constructor = operators.get(type(value))
    if constructor is not None:
        return constructor(*(to_formula(arg) for arg in value.args))
    if isinstance(value, (Nand, Nor, Xnor)):
        constructor = AND if isinstance(value, Nand) else OR if isinstance(value, Nor) else XOR
        return NOT(constructor(*(to_formula(arg) for arg in value.args)))
    if isinstance(value, AppliedPredicate):
        return to_local_predicate(value)
    return expr


@lru_cache(maxsize=3)
def _known_template(numbers: bool, matrices: bool) -> tuple[
    list[LocalPredicate], tuple[tuple[int, ...], ...],
]:
    clauses: set[Any] = set()
    if numbers:
        clauses.update(get_all_known_number_facts())
    if matrices:
        clauses.update(get_all_known_matrix_facts())
    sympy_predicates = sorted({lit.lit for clause in clauses for lit in clause}, key=str)
    predicates = [LocalQ.of(predicate.name) for predicate in sympy_predicates]
    encoding = {predicate: i + 1 for i, predicate in enumerate(sympy_predicates)}
    data = tuple(tuple(-encoding[lit.lit] if lit.is_Not else encoding[lit.lit]
                       for lit in clause) for clause in clauses)
    return predicates, data


def _extra_predicate_facts(subject: SymPyExpr) -> Iterable[object]:
    """Predicate-to-predicate facts missing from SymPy's known-fact table.

    These are universal implications, so they are asserted for every subject
    alongside the imported known facts.  They only mention local predicates
    and the opaque subject, so the core stays SymPy-free.
    """
    facts: list[object] = [
        IMPLIES(LocalQ.imaginary(subject), NOT(LocalQ.hermitian(subject))),
        IMPLIES(LocalQ.imaginary(subject), NOT(LocalQ.extended_real(subject))),
        IMPLIES(AND(LocalQ.real(subject), LocalQ.nonzero(subject)),
                NOT(LocalQ.antihermitian(subject))),
        IMPLIES(LocalQ.zero(subject), NOT(LocalQ.nonzero(subject))),
        IMPLIES(LocalQ.nonpositive(subject), NOT(LocalQ.positive(subject))),
        IMPLIES(LocalQ.nonnegative(subject), NOT(LocalQ.negative(subject))),
        IMPLIES(LocalQ.integer(subject),
                EQUIVALENT(LocalQ.odd(subject), NOT(LocalQ.even(subject)))),
    ]
    if isinstance(subject, Function):
        facts.append(IMPLIES(
            AND(*(LocalQ.commutative(arg) for arg in subject.args)),
            LocalQ.commutative(subject)))
        facts.append(IMPLIES(
            OR(*(NOT(LocalQ.commutative(arg)) for arg in subject.args)),
            NOT(LocalQ.commutative(subject))))
    return facts


def _negated_predicates(formula: object) -> set[object]:
    """Applied predicates that occur negated in a normalized formula."""
    if not isinstance(formula, Formula):
        return set()
    if formula.op == "not" and isinstance(formula.args[0], LocalAppliedPredicate):
        return {formula.args[0]}
    negated: set[object] = set()
    for arg in formula.args:
        negated |= _negated_predicates(arg)
    return negated


class SympyAdapter:
    def relevance_keys(self, atom: Any) -> set[SymPyExpr]:
        if isinstance(atom, LocalAppliedPredicate):
            keys: set[SymPyExpr] = set()
            for argument in atom.arguments:
                keys.update(cast("Any", argument).atoms(Symbol))
            return keys
        return cast("set[SymPyExpr]", atom.atoms(Symbol))

    def subjects(self, atom: Any) -> Iterable[object]:
        if isinstance(atom, (LocalAppliedPredicate, AppliedPredicate)):
            return atom.arguments
        return (atom,)

    def fact_subjects(self, atom: Any) -> Iterable[object]:
        if isinstance(atom, (LocalAppliedPredicate, AppliedPredicate)):
            return atom.arguments
        return ()

    def facts_for(self, subject: SymPyExpr) -> Iterable[object]:
        return (to_formula(fact) for fact in class_fact_registry(subject))

    def add_known_facts(self, subjects: Iterable[SymPyExpr], db: ClauseDB,
                        assumptions: object = True) -> None:
        subjects = list(subjects)
        numbers = any(expr.kind in (NumberKind, UndefinedKind) for expr in subjects)
        matrices = any(expr.kind == MatrixKind(NumberKind) for expr in subjects)
        predicates, clauses = _known_template(numbers, matrices)
        negated = _negated_predicates(assumptions)
        symbols: set[SymPyExpr] = set()
        for subject in subjects:
            symbols.update(cast("Any", subject).atoms(Symbol))
        for subject in subjects:
            mapping: list[int | None] = [None] + [
                db.literal(predicate(subject)) for predicate in predicates
            ]
            for clause in clauses:
                literals = [
                    cast(int, mapping[lit]) if lit > 0
                    else -cast(int, mapping[-lit])
                    for lit in clause
                ]
                db.add_clause(literals)
            for fact in _extra_predicate_facts(subject):
                assert_formula(fact, db)
        # SymPy treats symbols as commutative unless an assumption denies it.
        for symbol in symbols:
            if LocalQ.commutative(symbol) not in negated:
                assert_formula(LocalQ.commutative(symbol), db)
