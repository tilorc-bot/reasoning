"""Persistent known-facts compilation and per-subject binding reuse.

``add_known_facts`` instantiates a fixed finite theory: the vendored
known-facts template is translated into integer clauses once (lazily, on
first use) and each query only binds its subjects into the shared block.
These tests lock that structure down:

- the compiled block is built once and reused across many queries with
  distinct symbols (instrumented construction counter),
- per-subject bindings are reused across fresh databases whenever the
  variable layout repeats (the only layout ``satask`` produces),
- replay leaves every receiving database exactly as the previous
  per-clause re-emission did — clauses, auxiliaries, and the atom
  encoding are compared byte for byte against the oracle,
- answers are unchanged across a broad battery: the full-pipeline oracle
  over every ordered predicate pair in both polarities, and the issue #3
  harness shapes.
"""
from __future__ import annotations

from typing import Any

import pytest
from sympy import Abs, Add, And, Not, Q, sqrt, Symbol
from sympy.core.relational import Eq
from sympy.matrices.expressions.matexpr import MatrixSymbol

from reasoning import sympy_adapter
from reasoning.clauses import ClauseDB, SharedClauses, assert_formula, iter_atoms
from reasoning.discovery import discover_facts
from reasoning.knownfacts import MATRIX_PREDICATES, NUMBER_PREDICATES
from reasoning.satask import (
    _satask_pipeline, get_all_relevant_facts, normalize, satask,
)
from reasoning.sympy_adapter import (
    SympyAdapter, _shared_known_facts, _subject_bindings, _known_template,
)

x, y, z = Symbol("x"), Symbol("y"), Symbol("z")
A = MatrixSymbol("A", 2, 2)


@pytest.fixture(autouse=True)
def isolate_caches():
    """Every test starts from cold template and binding caches."""
    _shared_known_facts.cache_clear()
    _subject_bindings._cache.clear()
    _satask_memoized_clear()
    yield
    _shared_known_facts.cache_clear()
    _subject_bindings._cache.clear()
    _satask_memoized_clear()


def _satask_memoized_clear() -> None:
    from reasoning.satask import _satask_memoized
    _satask_memoized.cache_clear()


@pytest.fixture()
def build_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count SharedClauses constructions across the test."""
    calls = []
    original = SharedClauses.__init__

    def counting(self: SharedClauses, *args: Any, **kwargs: Any) -> None:
        calls.append(1)
        original(self, *args, **kwargs)

    monkeypatch.setattr(SharedClauses, "__init__", counting)
    return calls


def oracle_db(prop: Any, assump: Any) -> tuple[
        list[frozenset[int]], list[int], list[tuple[Any, int]]]:
    """Database contents as the per-clause re-emission produced them."""
    db = get_all_relevant_facts(normalize(prop), normalize(assump), True, None)
    assert_formula(normalize(assump), db)
    return (sorted(frozenset(clause) for clause in db.data),
            sorted(db.auxiliaries),
            sorted(((atom, variable) for atom, variable in db.encoding.items()),
                   key=lambda item: (item[0].name, repr(item[0].arguments))))


def current_db(prop: Any, assump: Any) -> tuple[
        list[frozenset[int]], list[int], list[tuple[Any, int]]]:
    """Database contents through the shared-block path."""
    db = get_all_relevant_facts(normalize(prop), normalize(assump), True, None)
    assert_formula(normalize(assump), db)
    return (sorted(frozenset(clause) for clause in db.data),
            sorted(db.auxiliaries),
            sorted(((atom, variable) for atom, variable in db.encoding.items()),
                   key=lambda item: (item[0].name, repr(item[0].arguments))))


# ---------------------------------------------------------------------------
# template reuse actually reuses
# ---------------------------------------------------------------------------

def test_shared_block_is_built_once_across_queries(build_counter) -> None:
    for index in range(25):
        symbol = Symbol(f"reuse{index}")
        # Composite assumptions defeat the fast path, exercising the
        # known-facts pipeline on every iteration.
        assert satask(Q.real(symbol),
                      Q.rational(symbol) & Q.commutative(symbol)) is True
        assert satask(Q.integer(symbol) & Q.real(symbol),
                      Q.even(symbol)) is True
    # One block per template selection ever requested, never per call.
    assert 1 <= len(build_counter) <= 4


def test_binding_cache_is_actually_hit() -> None:
    # Poison the minting path; a warm subject must reuse its binding.
    adapter = SympyAdapter()
    db1 = ClauseDB()
    adapter.add_known_facts([x], db1)
    binding1 = _subject_bindings._cache[(True, False, x)][0]

    def explode(atom: Any) -> int:
        raise AssertionError("db.literal must not run on a binding cache hit")

    db2 = ClauseDB()
    monkey_literal = ClauseDB.literal
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(ClauseDB, "literal", explode)
        adapter.add_known_facts([x], db2)
    finally:
        monkeypatch.undo()
        del monkey_literal
    binding2 = _subject_bindings._cache[(True, False, x)][0]
    assert binding1 == binding2
    assert db2.encoding[iter_next_atom()] == 1


def iter_next_atom() -> Any:
    predicates, _ = _known_template(True, False)
    return predicates[0](x)


def test_binding_cache_hit_replicates_db_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    # The cached-hit fill must leave encoding and symbols exactly as the
    # minting path would, including the atom objects themselves.
    adapter = SympyAdapter()
    minted = ClauseDB()
    adapter.add_known_facts([x, y], minted)

    fresh = ClauseDB()
    adapter.add_known_facts([x, y], fresh)  # second call: cache hits
    for atom, variable in minted.encoding.items():
        assert fresh.encoding[atom] == variable
        assert fresh.symbols[variable] is atom
    assert fresh._next_variable == minted._next_variable


def test_binding_cache_does_not_cross_template_selections() -> None:
    # A binding minted under the numbers-only template must never be
    # replayed against the merged (numbers+matrices) template.
    adapter = SympyAdapter()
    numbers_only = ClauseDB()
    adapter.add_known_facts([x], numbers_only)
    numbers_binding = _subject_bindings._cache[(True, False, x)][0]

    merged = ClauseDB()
    adapter.add_known_facts([A, x], merged)
    merged_binding = _subject_bindings._cache[(True, True, x)][0]
    assert len(merged_binding) > len(numbers_binding)


def test_stale_layout_falls_back_to_minting() -> None:
    # A database whose next free variable does not match the cached
    # binding's base must fall back to db.literal, not replay stale ids.
    from reasoning.predicates import AppliedPredicate as LocalApplied
    from reasoning.predicates import Predicate as LocalPredicate

    adapter = SympyAdapter()
    warm = ClauseDB()
    adapter.add_known_facts([x], warm)

    populated = ClauseDB()
    # Pre-occupy variable 1 so the cached layout cannot apply.
    populated.literal(LocalApplied(LocalPredicate("custom_predicate"), (x,)))
    adapter.add_known_facts([x], populated)
    assert populated.encoding[LocalApplied(LocalPredicate("custom_predicate"), (x,))] == 1
    predicates, _ = _known_template(True, False)
    for position, predicate in enumerate(predicates):
        assert populated.encoding[predicate(x)] == position + 2


# ---------------------------------------------------------------------------
# databases byte-identical to the re-emission oracle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prop,assump", [
    (Q.real(x), Q.rational(x)),
    (Q.real(x), True),
    (Q.real(x + y), And(Q.rational(x), Q.rational(y))),
    (Q.positive(x * y), And(Q.negative(x), Q.negative(y))),
    (Q.zero(Abs(x * y)), Q.zero(x)),
    (Q.real(sqrt(x)), Q.nonnegative(x)),
    (Q.diagonal(A), Q.invertible(A)),
    (Q.positive(Add(*[Symbol(f"pp{i}", positive=True) for i in range(20)],
                      *[Symbol(f"pn{i}", negative=True) for i in range(20)])),
     And(*[Q.positive(Symbol(f"pp{i}")) for i in range(20)],
          *[Q.negative(Symbol(f"pn{i}")) for i in range(20)])),
])
def test_database_matches_reemission_oracle(prop: Any, assump: Any) -> None:
    assert current_db(prop, assump) == oracle_db(prop, assump)


# ---------------------------------------------------------------------------
# answers unchanged across a broad battery
# ---------------------------------------------------------------------------

def literal(predicate: Any, subject: Any, positive: bool) -> Any:
    return predicate(subject) if positive else Not(predicate(subject))


@pytest.mark.parametrize("prop_sign", [True, False])
@pytest.mark.parametrize("assump_sign", [True, False])
def test_battery_number_predicate_pairs(prop_sign: bool, assump_sign: bool) -> None:
    # Every ordered pair of known number predicates, both polarities, over
    # fresh subjects; the full pipeline is the oracle.
    for name in NUMBER_PREDICATES:
        prop = getattr(Q, name, None)
        if prop is None:
            continue
        for assump_name in NUMBER_PREDICATES:
            assump = getattr(Q, assump_name, None)
            if assump is None:
                continue
            symbol = Symbol(f"b_{name}_{assump_name}")
            compare_with_oracle(literal(prop, symbol, prop_sign),
                                literal(assump, symbol, assump_sign))


def test_battery_matrix_predicate_pairs() -> None:
    for prop_name in MATRIX_PREDICATES:
        for assump_name in MATRIX_PREDICATES:
            for prop_sign in (True, False):
                prop = getattr(Q, prop_name)
                assump = getattr(Q, assump_name)
                matrix = MatrixSymbol(f"m_{prop_name}_{assump_name}_{prop_sign}", 2, 2)
                compare_with_oracle(
                    prop(matrix) if prop_sign else Not(prop(matrix)), assump(matrix))


def test_battery_no_assumptions_and_composites() -> None:
    for name in NUMBER_PREDICATES + MATRIX_PREDICATES:
        predicate = getattr(Q, name, None)
        if predicate is None:
            continue
        compare_with_oracle(predicate(x))
        compare_with_oracle(Not(predicate(x)))
    # Composite propositions/assumptions, relations, mixed subjects, and
    # the shapes the memo tests use.
    compare_with_oracle(Q.real(x) & Q.nonnegative(x), Q.positive(x))
    compare_with_oracle(Q.zero(x * y), Q.zero(x))
    compare_with_oracle(Eq(x, x), Q.real(x))
    compare_with_oracle(Q.real(x + y), Q.rational(x) & Q.rational(y))
    compare_with_oracle(Q.positive(Abs(x)), Q.real(x))
    compare_with_oracle(Q.real(sqrt(x)), Q.nonnegative(x))
    compare_with_oracle(Q.real(x), ~Q.real(x))
    compare_with_oracle(Q.real(x), Q.imaginary(x))
    with pytest.raises(ValueError):
        satask(Q.real(x), Q.real(x) & ~Q.real(x))
    with pytest.raises(TypeError):
        satask(x, Q.real(x))


def test_battery_issue3_harness_shapes() -> None:
    # The 13 shapes of the issue #3 reproduction script, with fresh
    # subjects per case, against the full-pipeline oracle.
    from sympy import exp, sin

    def pair(prop: Any, assump: Any) -> None:
        compare_with_oracle(prop, assump)

    pair(Q.positive(x), Q.positive(x))
    pair(Q.real(Symbol("r1")), Q.rational(Symbol("r1")))
    pair(Q.integer(Symbol("e1")), Q.even(Symbol("e1")))
    pair(Q.positive(x + y), And(Q.positive(x), Q.positive(y)))
    pair(Q.positive(x * y), And(Q.negative(x), Q.negative(y)))
    pair(Q.positive(x + y), And(Q.real(x), Q.real(y)))
    pair(Q.real(x ** 2), Q.real(x))
    pair(Q.positive(exp(x)), Q.real(x))
    pair(Q.real(sin(x)), Q.real(x))
    pair(Q.nonnegative(Abs(x)), Q.real(x))
    pair(Q.real(sqrt(x)), Q.nonnegative(x))
    four = [Symbol("f1", positive=True), Symbol("f2", negative=True)]
    pair(Q.positive(four[0] + four[1] + four[0] + four[1]),
         And(Q.positive(four[0]), Q.negative(four[1])))
    big = [Symbol(f"bg{i}", positive=True) for i in range(40)]
    pair(Q.positive(Add(*big)), And(*[Q.positive(v) for v in big]))


def compare_with_oracle(prop: Any, assump: Any = True,
                        **kw: Any) -> None:
    """Assert the public entry and the full pipeline agree bit for bit."""
    expected = _satask_pipeline(normalize(prop), normalize(assump),
                                kw.get("use_known_facts", True),
                                kw.get("iterations"), kw.get("early_return", False),
                                kw.get("use_lra_theory", False))
    assert satask(prop, assump, **kw) is expected
