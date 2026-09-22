"""Self-tests for :mod:`reasoning.tests.refine_harness`."""
from __future__ import annotations

import importlib
import pkgutil
import re

import pytest
from sympy.assumptions.ask import Q
from sympy.assumptions.ask import ask as sympy_ask
from sympy.abc import x
from sympy.functions.elementary.complexes import Abs

import reasoning.refine.handlers as handlers_package
from reasoning.tests.refine_harness import (
    assert_refines_like_sympy,
    assert_refinement_valid,
    recording_ask,
    reference_ask,
    scripted_ask,
    stub_ask,
    use_ask,
)


def test_reference_ask_restores_state() -> None:
    import reasoning.refine._upstream as upstream

    original = upstream.ask
    with reference_ask():
        assert upstream.ask is sympy_ask
    assert upstream.ask is original


def test_reference_ask_matches_sympy() -> None:
    assert_refines_like_sympy(Abs(x), Q.positive(x))


def test_reference_ask_detects_wrong_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reasoning.refine._upstream as upstream

    monkeypatch.setitem(upstream.handlers_dict, "Abs", lambda expr, assumptions: -expr.args[0])
    with pytest.raises(AssertionError, match="sympy.refine gives"):
        assert_refines_like_sympy(Abs(x), Q.positive(x))


def test_oracle_accepts_valid_refinement() -> None:
    assert_refinement_valid(x + 1, True, 1 + x)
    assert_refinement_valid(Abs(x), Q.positive(x), x)


def test_oracle_catches_invalid_refinement() -> None:
    with pytest.raises(AssertionError, match="invalid"):
        assert_refinement_valid(x + 1, True, x - 1)


def test_oracle_needs_satisfying_sample() -> None:
    from sympy.core.numbers import oo

    with pytest.raises(AssertionError, match="no satisfying sample"):
        assert_refinement_valid(x, Q.infinite(x), x)
    assert_refinement_valid(x, Q.infinite(x), x, values={x: [oo]})


def test_stub_ask() -> None:
    fake = stub_ask({str(Q.positive(x)): True})
    assert fake(Q.positive(x), True) is True
    assert fake(Q.negative(x), True) is None


def test_scripted_ask() -> None:
    fake, log = scripted_ask([True, None])
    assert fake(Q.positive(x), True) is True
    assert fake(Q.positive(x), True) is None
    assert fake(Q.positive(x), True) is None
    assert len(log) == 3


def test_recording_ask_logs_with_stub() -> None:
    fake, log = recording_ask({str(Q.positive(x)): True})
    assert fake(Q.positive(x), True) is True
    assert fake(Q.negative(x), True) is None
    assert [entry[2] for entry in log] == [True, None]


def test_use_ask_patches_module_attribute() -> None:
    import reasoning.refine._upstream as upstream

    fake = stub_ask({})
    with use_ask(fake):
        assert upstream.ask is fake
    assert upstream.ask is not fake


def test_no_duplicate_handler_keys() -> None:
    path = getattr(handlers_package, "__path__")
    owners: dict[str, list[str]] = {}
    pattern = re.compile(r"handlers_dict\[['\"]([^'\"]+)['\"]\]\s*=")
    for info in pkgutil.iter_modules(path):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{handlers_package.__name__}.{info.name}")
        source_file = getattr(module, "__file__")
        assert source_file is not None
        with open(source_file) as handle:
            source = handle.read()
        for key in pattern.findall(source):
            owners.setdefault(key, []).append(module.__name__)
    duplicates = {key: names for key, names in owners.items() if len(names) > 1}
    assert not duplicates, f"duplicate handler keys registered: {duplicates}"
