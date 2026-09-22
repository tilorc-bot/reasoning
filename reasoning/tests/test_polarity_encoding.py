"""Polarity-aware distribution of CNF-able antecedents (issue #2).

``assert_formula`` compiles ``Implies(Or(And-of-literals...), consequent)``
(and the right-nested form with a conjunction prefix) by distributing in the
negative polarity: one clause per disjunct, no Tseitin auxiliaries.  These
tests lock down

- the quadratic-to-linear clause/auxiliary counts of the Add
  sign-determination handler facts,
- that consequent-position Or-of-Ands still goes through Tseitin unchanged,
- a strong equivalence property: for every total assignment (exhaustive up
  to 8 atoms, random beyond), the asserted formula is true exactly when all
  emitted clauses are satisfied.
"""
from itertools import product
import random

import pytest
from sympy import Add, Q, Symbol

from reasoning.clauses import (
    AND, IMPLIES, NOT, OR, ClauseDB, Formula, assert_formula, compile_formula,
    iter_atoms,
)
from reasoning.sathandlers import class_fact_registry


def _formula_value(formula: object, values: dict[object, bool]) -> bool:
    if formula is True:
        return True
    if formula is False:
        return False
    if not isinstance(formula, Formula):
        return values[formula]
    args = [_formula_value(arg, values) for arg in formula.args]
    if formula.op == "and":
        return all(args)
    if formula.op == "or":
        return any(args)
    if formula.op == "not":
        return not args[0]
    if formula.op == "implies":
        return not args[0] or args[1]
    raise AssertionError(formula.op)


def _clauses_hold(db: ClauseDB, values: dict[object, bool]) -> bool:
    """Every emitted clause is satisfied under the atom assignment."""
    assignment = {db.literal(atom): value for atom, value in values.items()}
    return _clauses_hold_variables(db, assignment)


def _clauses_hold_variables(db: ClauseDB,
                            assignment: dict[int, bool]) -> bool:
    return all(any(assignment[abs(literal)] == (literal > 0) for literal in clause)
               for clause in db.data)


def _can_extend(db: ClauseDB, values: dict[object, bool]) -> bool:
    """Some assignment of the auxiliary variables satisfies all clauses."""
    fixed = {db.literal(atom): value for atom, value in values.items()}
    free = [variable for variable in db.variables if variable not in fixed]
    for bits in product((False, True), repeat=len(free)):
        extended = dict(fixed)
        extended.update(zip(free, bits))
        if _clauses_hold_variables(db, extended):
            return True
    return False


def _exactly_one(items: tuple) -> object:
    return OR(*(AND(item, *(NOT(other) for other in items if other is not item))
                for item in items))


def _assert_equivalent(formula: object) -> ClauseDB:
    """Assert *formula* and check clauses ⟺ formula over every assignment."""
    db = ClauseDB()
    assert_formula(formula, db)
    atoms = tuple(dict.fromkeys(iter_atoms(formula)))
    assert len(atoms) <= 10
    for bits in product((False, True), repeat=len(atoms)):
        values = dict(zip(atoms, bits))
        assert _clauses_hold(db, values) == _formula_value(formula, values)
    return db


def _canonical(db: ClauseDB) -> tuple:
    """Numbering-invariant clause structure (atom names, aux by first use)."""
    renamed: dict[int, str] = {}

    def name(literal: int) -> str:
        variable = abs(literal)
        if variable in db.auxiliaries:
            if variable not in renamed:
                renamed[variable] = f"@{len(renamed) + 1}"
            term = renamed[variable]
        else:
            term = repr(db.symbols[variable])
        return term if literal > 0 else "~" + term

    return tuple(frozenset(name(literal) for literal in clause)
                 for clause in db.data)


def _assert_matches_reference_tseitin(formula: object) -> ClauseDB:
    """Non-fast-pathed shapes must emit exactly the Tseitin clauses."""
    db = ClauseDB()
    assert_formula(formula, db)
    assert db.auxiliaries  # no distribution happened
    reference = ClauseDB()
    literal = compile_formula(formula, reference)
    reference.add_clause((literal,))
    assert _canonical(db) == _canonical(reference)
    assert len(db.auxiliaries) == len(reference.auxiliaries)
    return db


# Reproducer shapes from issue #2 (Add sign-determination handler facts).

def _sign_fact_disjuncts(n: int) -> object:
    return OR(*(AND(*[('p%d' % (i + 1)) if i == j else NOT('p%d' % (i + 1))
                      for i in range(n)]) for j in range(n)))


@pytest.mark.parametrize("n", [4, 10, 40])
def test_negative_position_counts_drop_from_quadratic_to_linear(n: int) -> None:
    # Before: n=4 -> 37 clauses/8 aux, n=10 -> 139/14, n=40 -> 1729/44.
    nested = IMPLIES(AND(*['r%d' % (i + 1) for i in range(n)]),
                     IMPLIES(_sign_fact_disjuncts(n), 'q'))
    db = ClauseDB()
    assert_formula(nested, db)
    assert (len(db.data), len(db.auxiliaries)) == (n, 0)

    plain = IMPLIES(_sign_fact_disjuncts(n), NOT('q'))
    db = ClauseDB()
    assert_formula(plain, db)
    assert (len(db.data), len(db.auxiliaries)) == (n, 0)


def test_consequent_position_still_compiles_through_tseitin() -> None:
    _assert_matches_reference_tseitin(IMPLIES('a', OR(AND('b', 'c'), AND('d', 'e'))))


def test_consequent_position_nested_implies_still_compiles_through_tseitin() -> None:
    _assert_matches_reference_tseitin(IMPLIES(OR(AND('a', 'b'), AND('c', 'd')),
                                              IMPLIES('q', 'r')))


def test_complex_antecedent_disjuncts_still_compile_through_tseitin() -> None:
    # An Or inside an And disjunct is not a conjunction of literals.
    _assert_matches_reference_tseitin(Formula("implies", (
        Formula("or", (
            Formula("and", ('a', Formula("or", ('b', 'c')))),
            AND('d', 'e'))),
        'q')))


# Exhaustive equivalence: fast-path family emits no auxiliaries, and the
# clause set is true exactly when the formula is.

@pytest.mark.parametrize("formula", [
    IMPLIES(OR(AND('a', 'b'), AND('c', 'd')), 'q'),
    IMPLIES(OR('a', 'b', 'c'), NOT('q')),
    IMPLIES(OR(AND('a', 'b', 'c'), AND('d', 'e', 'f')), OR('q', NOT('r'))),
    IMPLIES(AND('a', 'b'),
            IMPLIES(OR(AND('c', 'd'), AND('e', 'f')), NOT('g'))),
    IMPLIES(OR(AND('a'), AND('b', 'c'), 'd', AND('e', 'f')), 'q'),
    IMPLIES(AND('a', 'b'),
            IMPLIES(OR(AND('a', 'c'), AND('b', 'd')), 'q')),
    # Constants inside the antecedent (bypass the simplifying constructors).
    Formula("implies", (
        Formula("or", (
            Formula("and", ('a', True)),
            Formula("and", (False, 'b')),
            AND('c', 'd'))),
        'q')),
    # A self-contradictory disjunct contributes a tautological clause.
    Formula("implies", (
        Formula("or", (
            Formula("and", ('a', NOT('a'))),
            AND('b', 'c'))),
        'q')),
    # Duplicated literals and single-disjunct Or.
    Formula("implies", (
        Formula("or", (
            Formula("and", ('a', 'a', NOT('b'))),
            Formula("and", ('c', NOT('d'))))),
        'q')),
    Formula("implies", (Formula("or", (AND('a', 'b'),)), 'q')),
    # A constant consequent.
    Formula("implies", (OR(AND('a', 'b'), AND('c', 'd')), False)),
])
def test_fast_path_formula_equivalent_to_clauses_exhaustively(formula: object) -> None:
    db = _assert_equivalent(formula)
    assert db.auxiliaries == set()


@pytest.mark.parametrize("formula", [
    IMPLIES('a', OR(AND('b', 'c'), AND('d', 'e'))),
    Formula("implies", (
        Formula("or", (
            AND('a', 'b'),
            Formula("or", ('c', 'd')))),
        'q')),
])
def test_fallback_formula_equisatisfiable_exhaustively(formula: object) -> None:
    db = ClauseDB()
    assert_formula(formula, db)
    assert db.auxiliaries
    atoms = tuple(dict.fromkeys(iter_atoms(formula)))
    for bits in product((False, True), repeat=len(atoms)):
        values = dict(zip(atoms, bits))
        assert _can_extend(db, values) == _formula_value(formula, values)


# Random shapes: exhaustive up to 8 atoms, sampled beyond.

def _random_fast_path_formula(rng: random.Random, atoms: list[str]) -> object:
    disjuncts = []
    for _ in range(rng.randint(2, 4)):
        width = rng.randint(1, 3)
        literals = [atom if rng.random() < 0.5 else NOT(atom)
                    for atom in rng.sample(atoms, min(width, len(atoms)))]
        disjuncts.append(AND(*literals) if len(literals) > 1 else literals[0])
    consequent_literals = [atom if rng.random() < 0.5 else NOT(atom)
                           for atom in rng.sample(atoms, rng.randint(1, 2))]
    consequent = OR(*consequent_literals)
    disjunction = Formula("or", tuple(disjuncts)) if len(disjuncts) > 1 else disjuncts[0]
    if rng.random() < 0.5:
        prefix = [atom if rng.random() < 0.5 else NOT(atom)
                  for atom in rng.sample(atoms, rng.randint(1, 2))]
        return IMPLIES(AND(*prefix), IMPLIES(disjunction, consequent))
    return IMPLIES(disjunction, consequent)


def test_random_fast_path_formulas_equivalent_to_clauses() -> None:
    rng = random.Random(20260922)
    checked = 0
    for trial in range(24):
        size = 8 if trial < 12 else rng.randint(9, 12)
        atoms = [f'v{trial}_{index}' for index in range(size)]
        formula = _random_fast_path_formula(rng, atoms)
        db = ClauseDB()
        assert_formula(formula, db)
        assert db.auxiliaries == set()
        if size <= 8:
            assignments = (dict(zip(atoms, bits))
                           for bits in product((False, True), repeat=size))
        else:
            assignments = (dict(zip(atoms, rng.choices([False, True], k=size)))
                           for _ in range(256))
        for values in assignments:
            checked += 1
            assert _clauses_hold(db, values) == _formula_value(formula, values)
    assert checked >= 12 * 2 ** 8 + 12 * 256


def test_random_fallback_formulas_equisatisfiable() -> None:
    rng = random.Random(409)
    for trial in range(8):
        atoms = [f'w{trial}_{index}' for index in range(5)]
        formula = IMPLIES(rng.choice(atoms),
                          OR(AND(rng.choice(atoms), rng.choice(atoms)),
                             AND(rng.choice(atoms), rng.choice(atoms))))
        db = ClauseDB()
        assert_formula(formula, db)
        assert db.auxiliaries
        for bits in product((False, True), repeat=len(atoms)):
            values = dict(zip(atoms, bits))
            assert _can_extend(db, values) == _formula_value(formula, values)


# The real Add sign-determination handler facts, exactly as discovery
# asserts them, verified exhaustively and now auxiliary-free.

def test_add_handler_sign_facts_equivalent_and_auxiliary_free() -> None:
    terms = [Symbol(f's{index}') for index in range(4)]
    expr = Add(*terms)
    db = ClauseDB()
    for fact in sorted(class_fact_registry(expr), key=repr):
        assert_formula(fact, db)
    assert db.auxiliaries == set()
    assert len(db.data) == 13  # 5 flat + 4 (exactly-one integer) + 4 (nested irrational)

    for fact in sorted(class_fact_registry(expr), key=repr):
        fact_db = _assert_equivalent(fact)
        assert fact_db.auxiliaries == set()
