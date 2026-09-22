"""The boundary between SymPy expressions and the propositional core."""
from functools import lru_cache
from typing import Any, Callable, Iterable, TypeAlias, cast

from sympy import S, Symbol
from sympy.assumptions.assume import AppliedPredicate
from sympy.core.kind import NumberKind, UndefinedKind
from sympy.core.relational import Eq, Ne, Gt, Lt, Ge, Le
from sympy.logic.boolalg import (
    And, Or, Not, Implies, Equivalent, Xor, Xnor, ITE, Nand, Nor,
)
from sympy.matrices.kind import MatrixKind

from .clauses import (
    ClauseDB, Formula, SharedClauses, AND, OR, NOT, IMPLIES, EQUIVALENT,
    XOR, ITE as IF, iter_atoms,
)
from .knownfacts import template as known_facts_template
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
    names, clauses = known_facts_template(numbers, matrices)
    predicates = [LocalQ.of(name) for name in names]
    return predicates, clauses


@lru_cache(maxsize=4)
def _shared_known_facts(numbers: bool, matrices: bool) -> SharedClauses:
    """Compile the known-facts theory into a shared clause block.

    The known-facts template is a fixed finite theory: the same clauses are
    needed in every query, one per subject with only the atom bindings
    varying.  Compiling it once into a :class:`~reasoning.clauses.
    SharedClauses` block removes the per-call re-translation; each query
    still gets its own database and replays its own copies of the clauses
    into it, so nothing is shared with the solver at solve time.
    """
    predicates, clauses = _known_template(numbers, matrices)
    return SharedClauses(clauses, width=len(predicates))


class _SubjectBindings:
    """Intern the per-subject template bindings across queries.

    Each subject's binding is a tuple of variable ids, one per template
    predicate, minted in the receiving database by ``db.literal``.  Variable
    ids are not stable across databases, so a cached binding cannot be
    replayed into a fresh database directly — but its *layout* is: whenever
    the minting would start at the same base id (every atom fresh, the only
    shape ``satask`` produces), the ids repeat exactly, and the minting
    loop collapses to two dict fills.  The applied atoms are cached
    alongside the binding so a hit fills ``encoding`` and ``symbols``
    without rebuilding or re-hashing them; a hit therefore leaves the
    database exactly as a sequence of ``db.literal`` calls would have.
    Bindings that would not repeat (atoms pre-existing in the database) are
    simply not cached, keeping every other caller on the minting path.
    """

    __slots__ = ("_cache",)

    def __init__(self) -> None:
        self._cache: dict[tuple[bool, bool, object],
                          tuple[tuple[int, ...], tuple[LocalAppliedPredicate, ...]]] = {}

    def bind(self, subject: SymPyExpr, predicates: list[LocalPredicate],
             db: ClauseDB, selection: tuple[bool, bool]) -> tuple[int, ...]:
        # The selection is part of the key: template selections have
        # different widths, and a layout minted under one must never be
        # replayed against another.
        key = (selection[0], selection[1], subject)
        cached = self._cache.get(key)
        if cached is not None and db._next_variable == cached[0][0]:
            binding, atoms = cached
            encoding = db.encoding
            symbols = db.symbols
            for variable, atom in zip(binding, atoms):
                encoding[atom] = variable
                symbols[variable] = atom
            db._next_variable += len(binding)
            return binding
        atoms = tuple(predicate(subject) for predicate in predicates)
        binding = tuple(db.literal(atom) for atom in atoms)
        if db._next_variable == binding[0] + len(binding):
            self._cache[key] = (binding, atoms)
        return binding


_subject_bindings = _SubjectBindings()


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

    def add_known_facts(self, subjects: Iterable[SymPyExpr], db: ClauseDB) -> None:
        numbers = any(expr.kind in (NumberKind, UndefinedKind) for expr in subjects)
        matrices = any(expr.kind == MatrixKind(NumberKind) for expr in subjects)
        block = _shared_known_facts(numbers, matrices)
        predicates, _ = _known_template(numbers, matrices)
        selection = (numbers, matrices)
        for subject in subjects:
            block.replay(db, _subject_bindings.bind(subject, predicates, db,
                                                    selection))
