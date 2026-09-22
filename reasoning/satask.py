"""SymPy-facing entry points for the independent SAT reasoning core."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterable, cast

from .clauses import ClauseDB, assert_formula, compile_formula, iter_atoms
from .discovery import discover_facts, relevant_subjects
from .engine import ReasoningEngine
from .lra_adapter import build_lra_theory
from .sympy_adapter import (
    NormalizedFormula, SympyAdapter, normalize, to_formula,
)
from .sympy_types import SymPyExpr


def _memo_argument(value: SymPyExpr | bool) -> SymPyExpr:
    """Return a cache key for a public input without bool/int collisions.

    Python bools are ints (``True == 1`` and ``False == 0`` compare equal and
    hash equal), so raw values would let a cached ``satask(True, ...)`` answer
    a later ``satask(1, ...)``, which raises TypeError.  Keying on the SymPy
    counterparts (as ``normalize`` interprets them) separates the values; the
    keys stay hashable and every other value is unaffected.  SymPy objects
    themselves never equal Python numbers they are not equal to (SymPy Booleans
    are ``Basic``, so ``hash(S.true) != hash(1)``), and SymPy Booleans mapped
    through :func:`normalize` are exactly these constants, while raw SymPy
    expressions still key on identity-by-value hashing.
    """
    if value is True:
        from sympy import true
        return true
    if value is False:
        from sympy import false
        return false
    return value


def _memo_iteration(iterations: object) -> tuple[Any, object] | None:
    """Return a cache key for the iteration limit without int collisions.

    The result must be unhashable-safe: an unknown type raises TypeError at
    key construction, and :func:`satask` then recomputes uncached.  Tagging
    with the runtime type separates values that compare and hash equal on
    the value alone, such as ``False``, ``0.0``, or ``numpy.int64(0)``
    against ``0``: the former pairs raise ValueError while ``0`` is valid.
    """
    if iterations is None:
        return None
    return _IterationKey((type(iterations), iterations))


class _IterationKey(tuple):
    """Marker subclass wrapping an iteration limit inside the memo key."""


def _unwrap(iterations: object) -> object | None:
    # Invert _memo_iteration by marker type, never by value inspection.
    if type(iterations) is _IterationKey:
        return iterations[1]
    return iterations


def _iteration_limit(iterations: object) -> int | None:
    # Keep accepting the former oo default at the public boundary.
    from sympy import oo
    if iterations is None or iterations == oo:
        return None
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 0:
        raise ValueError("iterations must be a nonnegative integer or None")
    return iterations


def satask(proposition: SymPyExpr | bool, assumptions: SymPyExpr | bool = True,
           use_known_facts: bool = True, iterations: object = None,
           early_return: bool = False,
           use_lra_theory: bool = False) -> bool | None:
    """Return True, False, or None according to the supplied assumptions.

    Expression facts are discovered breadth-first, processing each expression
    once. ``iterations=None`` runs until no unseen expression remains; zero
    disables expression-fact discovery. Known predicate facts are controlled
    independently by ``use_known_facts``.

    By default inconsistent assumptions raise ValueError. ``early_return``
    permits an answer from unit propagation while trusting consistency.

    ``use_lra_theory`` additionally interprets the linear relations among the
    discovered ``Q.eq``/``Q.gt``/``Q.lt``/``Q.ge``/``Q.le`` atoms and lets the
    linear arithmetic solver prune inconsistent assignments. It is opt-in
    because the theory changes the search and only helps formulas whose
    Boolean structure leaves relations undecided.

    Inputs are normalized by :func:`~reasoning.sympy_adapter.normalize`:
    Python Booleans and legacy CNF objects are accepted, any other non-SymPy
    value raises TypeError, and SymPy ``Q`` applications become local
    :mod:`reasoning.predicates` applications whose arguments are the original
    SymPy expressions.

    Results are memoized on the full argument tuple in a bounded LRU cache
    (``_MEMO_MAXSIZE`` entries), so repeated identical queries cost a dict
    lookup.  Exceptions are never cached: inconsistent assumptions raise
    again on every call.  Like the rest
    of the package, the cache assumes single-threaded use.
    """
    try:
        return _satask_memoized(_memo_argument(proposition),
                               _memo_argument(assumptions), use_known_facts,
                               _memo_iteration(iterations), early_return,
                               use_lra_theory)
    except TypeError:
        # The arguments are unhashable (lru_cache rejects them) or ``normalize``
        # rejected a non-expression input.  Recompute uncached so the original
        # result or error is produced exactly as before.
        return _satask(proposition, assumptions, use_known_facts, iterations,
                       early_return, use_lra_theory)


# Bound the memoization cache; each entry pins its key expressions.
_MEMO_MAXSIZE = 4096

@lru_cache(maxsize=_MEMO_MAXSIZE)
def _satask_memoized(proposition: SymPyExpr | bool, assumptions: SymPyExpr | bool,
                     use_known_facts: bool, iterations: object,
                     early_return: bool, use_lra_theory: bool) -> bool | None:
    return _satask(proposition, assumptions, use_known_facts,
                   _unwrap(iterations), early_return, use_lra_theory)


def _satask(proposition: SymPyExpr | bool, assumptions: SymPyExpr | bool,
            use_known_facts: bool, iterations: object,
            early_return: bool, use_lra_theory: bool) -> bool | None:
    prop_formula: NormalizedFormula = normalize(proposition)
    assump_formula: NormalizedFormula = normalize(assumptions)
    db = get_all_relevant_facts(prop_formula, assump_formula, use_known_facts, iterations)
    assert_formula(assump_formula, db)
    query = compile_formula(prop_formula, db)

    theories = []
    if use_lra_theory:
        lra, conflicts = build_lra_theory(db)
        for conflict in conflicts:
            db.add_clause(conflict)
        if lra is not None:
            theories.append(lra)

    engine = ReasoningEngine(db, theory_solvers=theories)
    return engine.ask(query, early_return=early_return)


def extract_predargs(proposition: object,
                     assumptions: object = None) -> set[object]:
    """Find subjects connected to the proposition through assumption symbols."""
    return relevant_subjects(to_formula(proposition),
                             to_formula(True if assumptions is None else assumptions),
                             SympyAdapter())


def find_symbols(proposition: object) -> set[object]:
    adapter = SympyAdapter()
    symbols: set[object] = set()
    for atom in iter_atoms(to_formula(proposition)):
        symbols.update(adapter.relevance_keys(atom))
    return symbols


def get_relevant_clsfacts(exprs: Iterable[object],
                          relevant_facts: ClauseDB | None = None,
                          ) -> tuple[set[object], ClauseDB]:
    """Encode one discovery round; return new subjects and a ClauseDB."""
    adapter = SympyAdapter()
    db = ClauseDB() if relevant_facts is None else relevant_facts
    following: set[object] = set()
    for expr in exprs:
        for fact in adapter.facts_for(expr):
            for atom in iter_atoms(fact):
                following.update(adapter.fact_subjects(atom))
            assert_formula(fact, db)
    return following - set(exprs), db


def get_all_relevant_facts(proposition: object, assumptions: object,
                           use_known_facts: bool = True,
                           iterations: object = None) -> ClauseDB:
    """Build integer clauses for expression and known predicate facts."""
    adapter = SympyAdapter()
    subjects = relevant_subjects(to_formula(proposition), to_formula(assumptions), adapter)
    db = ClauseDB()
    visited = discover_facts(subjects, db, adapter, _iteration_limit(iterations))
    if use_known_facts:
        adapter.add_known_facts(subjects | visited, db)
    return db
