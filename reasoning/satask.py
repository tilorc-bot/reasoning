"""SymPy-facing entry points for the independent SAT reasoning core."""
from __future__ import annotations

from typing import Iterable

from .clauses import ClauseDB, assert_formula, compile_formula, iter_atoms
from .discovery import discover_facts, relevant_subjects
from .engine import ReasoningEngine
from .sympy_adapter import (
    NormalizedFormula, SympyAdapter, normalize, to_formula,
)
from .sympy_types import SymPyExpr


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
           early_return: bool = False) -> bool | None:
    """Return True, False, or None according to the supplied assumptions.

    Expression facts are discovered breadth-first, processing each expression
    once. ``iterations=None`` runs until no unseen expression remains; zero
    disables expression-fact discovery. Known predicate facts are controlled
    independently by ``use_known_facts``.

    By default inconsistent assumptions raise ValueError. ``early_return``
    permits an answer from unit propagation while trusting consistency.

    Inputs are normalized by :func:`~reasoning.sympy_adapter.normalize`:
    Python Booleans and legacy CNF objects are accepted, any other non-SymPy
    value raises TypeError, and SymPy ``Q`` applications become local
    :mod:`reasoning.predicates` applications whose arguments are the original
    SymPy expressions.
    """
    prop_formula: NormalizedFormula = normalize(proposition)
    assump_formula: NormalizedFormula = normalize(assumptions)
    db = get_all_relevant_facts(prop_formula, assump_formula, use_known_facts, iterations)
    assert_formula(assump_formula, db)
    query = compile_formula(prop_formula, db)
    return ReasoningEngine(db).ask(query, early_return=early_return)


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
        adapter.add_known_facts(subjects | visited, db,
                                to_formula(assumptions))
    return db
