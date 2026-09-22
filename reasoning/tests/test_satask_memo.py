"""Memoization and fast-path behavior of :mod:`reasoning.satask`.

The optimizations inside ``satask`` must be semantically transparent: the
memoized public entry point and the fast path must return exactly what the
full pipeline returns for every query.  These tests treat the full pipeline
(:func:`reasoning.satask._satask_pipeline`, which builds the clause database,
runs discovery, and invokes the solver) as the oracle and compare against it
bit for bit, including raised exceptions.  The oracle deliberately bypasses
both the memoization and the fast path.
"""
from __future__ import annotations

from typing import Any

import pytest
from sympy import Abs, Not, Q, sqrt
from sympy import oo
from sympy.core.relational import Eq
from sympy.core.symbol import symbols
from sympy.matrices.expressions.matexpr import MatrixSymbol

from reasoning.knownfacts import MATRIX_PREDICATES, NUMBER_PREDICATES
from reasoning.satask import (
    _MEMO_MAXSIZE, _satask_pipeline, normalize, satask, _satask_memoized,
)

x, y = symbols("x y")
A = MatrixSymbol("A", 2, 2)


@pytest.fixture(autouse=True)
def clear_memo():
    """Isolate every test from cache state left behind by other tests."""
    _satask_memoized.cache_clear()
    yield
    _satask_memoized.cache_clear()


def oracle(prop: Any, assump: Any = True, **kw: Any) -> Any:
    """Run the full pipeline directly: no memoization, no fast path."""
    return _satask_pipeline(normalize(prop), normalize(assump),
                            kw.get("use_known_facts", True),
                            kw.get("iterations"), kw.get("early_return", False),
                            kw.get("use_lra_theory", False))


def compare(prop: Any, assump: Any = True, **kw: Any) -> None:
    """Assert public and full-pipeline answers agree bit for bit."""
    try:
        expected = oracle(prop, assump, **kw)
    except Exception as exc:  # noqa: BLE001 - the raise is reproduced below
        with pytest.raises(type(exc), match=f"^{__import__('re').escape(str(exc))}$"):
            satask(prop, assump, **kw)
        return
    assert satask(prop, assump, **kw) is expected


def literal(predicate: Any, positive: bool) -> Any:
    return predicate(x) if positive else Not(predicate(x))


def test_memo_returns_identical_repeated_results() -> None:
    # Warm cache: True, False, and None answers all survive repeated calls.
    assert satask(Q.real(x), Q.rational(x)) is True
    assert satask(Q.real(x), ~Q.real(x)) is False
    assert satask(Q.real(x)) is None
    assert satask(Q.positive(x), Q.positive(x)) is True
    for _ in range(3):
        assert satask(Q.real(x), Q.rational(x)) is True
        assert satask(Q.real(x), ~Q.real(x)) is False
        assert satask(Q.real(x)) is None


def test_memo_cache_is_actually_hit() -> None:
    # Poison every pipeline entry point; a warm repeat must not rerun them.
    import reasoning.satask as module

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the full pipeline must not run on a cache hit")

    assert satask(Q.real(x), Q.rational(x)) is True
    saved = {name: getattr(module, name)
             for name in ("normalize", "get_all_relevant_facts")}
    try:
        for name in saved:
            setattr(module, name, explode)
        assert satask(Q.real(x), Q.rational(x)) is True
    finally:
        for name, function in saved.items():
            setattr(module, name, function)


def test_memo_does_not_leak_across_assumptions_or_props() -> None:
    # Same proposition under different assumptions; same assumptions over
    # different propositions; also: cache order does not matter.
    pairs = [
        (Q.real(x), Q.rational(x)),          # True
        (Q.real(x), ~Q.rational(x)),         # None
        (Q.positive(x), Q.even(x)),          # None: different family
        (Q.integer(x), Q.even(x)),           # True
        (Q.real(x), Q.imaginary(x)),         # True via negative edge
        (Q.real(x), ~Q.imaginary(x)),        # None
        (Q.real(x) & Q.real(y), Q.rational(x) & Q.rational(y)),  # full pipeline
        (Q.real(x), Q.rational(y)),          # different subjects, full pipeline
    ]
    for prop, assump in pairs:
        compare(prop, assump)
    # Reverse stress: cache the None entries after the True entries.
    _satask_memoized.cache_clear()
    for prop, assump in reversed(pairs):
        compare(prop, assump)


def test_memo_never_mixes_boolean_and_integer_inputs() -> None:
    # Python bools compare and hash equal to 0/1, so a key on the raw values
    # would let satask(False) answer satask(0) or satask(True) answer
    # satask(1).  Booleans (valid queries) and integers (which normalize
    # rejects with TypeError) must stay apart in both argument positions.
    assert satask(False) is False
    with pytest.raises(TypeError):
        satask(0)
    assert satask(True) is True
    with pytest.raises(TypeError):
        satask(1)
    with pytest.raises(TypeError):
        satask(Q.real(x), 0)
    with pytest.raises(TypeError):
        satask(Q.real(x), 1)
    assert satask(Q.real(x), True) is None
    with pytest.raises(ValueError):
        satask(Q.real(x), False)


def test_memo_does_not_cache_exceptions() -> None:
    # Inconsistent assumptions raise on every call; the failure must not
    # poison later, valid queries over the same expressions.
    for _ in range(3):
        with pytest.raises(ValueError):
            satask(Q.real(x), Q.real(x) & ~Q.real(x))
    assert satask(Q.real(x)) is None
    assert satask(Q.real(x), Q.real(x)) is True


def test_memo_iteration_values_are_kept_apart() -> None:
    # iterations=0 is accepted while False and 0.0 raise ValueError; keys for
    # values that compare equal as numbers must not share cache slots.
    for value in (0, 5, oo):
        prop, assump = Q.real(x), Q.rational(x)
        assert satask(prop, assump, iterations=value) == oracle(
            prop, assump, iterations=value)
    with pytest.raises(ValueError):
        satask(Q.real(x), Q.rational(x), iterations=False)
    with pytest.raises(ValueError):
        satask(Q.real(x), Q.rational(x), iterations=0.0)
    with pytest.raises(ValueError):
        satask(Q.real(x), Q.rational(x), iterations="1")
    with pytest.raises(ValueError):
        satask(Q.real(x), Q.rational(x), iterations=-1)


def test_fast_path_matches_full_pipeline_on_leaf_cases() -> None:
    # The leaf regimes from the issue: declared facts and known single-hop
    # inferences, including a negated proposition and a negated assumption.
    for prop, assump in [
        (Q.positive(x), Q.positive(x)),
        (Q.real(x), Q.rational(x)),
        (Q.integer(x), Q.even(x)),
        (~Q.real(x), Q.rational(x)),
        (Q.real(x), ~Q.rational(x)),
        (Q.real(x), Q.imaginary(x)),
    ]:
        compare(prop, assump)


def test_lra_theory_disables_the_fast_path() -> None:
    # The LRA theory decides degenerate relation literals that the clause
    # database alone cannot, and can make a single literal assumption
    # inconsistent, so the fast path must never answer when it is enabled.
    # Every case here was answered wrongly (or without raising) by an earlier
    # fast path that ignored ``use_lra_theory``.
    for prop, assump, expected in [
        (Q.eq(x, x), ~Q.eq(x, x), ValueError),
        (Q.gt(x, x), Q.gt(x, x), ValueError),
        (Q.real(x), ~Q.eq(x, x), ValueError),
        (~Q.eq(x, x), True, False),
        (Q.gt(x, x), True, False),
        (~Q.gt(x, x), True, True),
        (Q.ge(x, x), True, True),
        (Q.le(x, x), True, True),
        (Q.eq(x, 0), Q.eq(x, 0), True),
        (Q.eq(x, y), Q.eq(x, y), True),
        (Q.real(x), Q.eq(x, 0), None),
        (Q.zero(x), Q.eq(x, 0), None),
    ]:
        compare(prop, assump, use_lra_theory=True)
        if expected is ValueError:
            with pytest.raises(ValueError):
                satask(prop, assump, use_lra_theory=True)
        else:
            assert satask(prop, assump, use_lra_theory=True) is expected


def test_not_fast_path_cases_still_work() -> None:
    # Composite propositions, differing subjects, relations, and transfer
    # facts must fall through to the full pipeline intact.
    compare(Q.real(x) & Q.nonnegative(x), Q.positive(x))
    compare(Q.zero(x * y), Q.zero(x))
    compare(Eq(x, x), Q.real(x))
    compare(Q.real(x + y), Q.rational(x) & Q.rational(y))
    compare(Q.positive(Abs(x)), Q.real(x))
    compare(Q.real(sqrt(x)), Q.nonnegative(x))
    with pytest.raises(TypeError):
        satask(x, Q.real(x))
    with pytest.raises(TypeError):
        satask("junk")


def test_inconsistent_assumptions_match() -> None:
    # Inconsistent assumptions raise through both the public entry point and
    # the full pipeline, identically, regardless of cache state.  The sample
    # contradiction mirrors test_satask_early_return in test_satask.py: it is
    # invisible to root-level unit propagation, so satask(early_return=True)
    # still answers without raising, and the fast path defers to the full
    # pipeline for every such composite assumption anyway.
    contradiction = (Q.real(x) & (Q.positive(x) | Q.negative(x))
                     & (Q.positive(x) >> Q.zero(x))
                     & (Q.negative(x) >> Q.zero(x)))
    public_raises(ValueError, Q.real(x), contradiction)
    assert satask(Q.real(x), contradiction, early_return=True) is True
    # Root-level-propagatable contradictions raise even with early_return:
    public_raises(ValueError, Q.real(x), Q.real(x) & ~Q.real(x))
    with pytest.raises(ValueError):
        satask(Q.real(x), Q.real(x) & ~Q.real(x), early_return=True)
    compare(Q.real(x), Q.positive(x) & Q.negative(x))
    compare(Q.positive(x), ~Q.positive(x))
    compare(Q.real(x), ~Q.real(x))


def public_raises(exception: type[BaseException],
                  prop: Any, assump: Any = True, **kw: Any) -> None:
    with pytest.raises(exception):
        satask(prop, assump, **kw)


def test_fast_path_matches_full_pipeline_single_hops_matrix() -> None:
    predicates = [getattr(Q, name) for name in MATRIX_PREDICATES]
    for prop in predicates:
        for assump in predicates:
            for prop_positive in (True, False):
                compare(prop(A) if prop_positive else Not(prop(A)), assump(A))


@pytest.mark.parametrize("prop_sign", [True, False])
@pytest.mark.parametrize("assump_sign", [True, False])
def test_fast_path_matches_full_pipeline_single_hops(
        prop_sign: bool, assump_sign: bool) -> None:
    # Exhaust the known-facts template directly: every ordered pair of known
    # number predicates, in both directions and both polarities.  The full
    # pipeline is the oracle; whatever pair is not a single hop is exercised
    # by it, so any fast-path divergence will show up.
    predicates = {name: getattr(Q, name) for name in NUMBER_PREDICATES
                  if getattr(Q, name, None) is not None}
    for prop_name in predicates:
        for assump_name in predicates:
            compare(literal(predicates[prop_name], prop_sign),
                    literal(predicates[assump_name], assump_sign))


def test_memo_size_policy_is_bounded() -> None:
    # Cache growth policy: a bounded LRU with a documented generous maxsize.
    assert _MEMO_MAXSIZE == 4096
