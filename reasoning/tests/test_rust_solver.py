"""Unit tests for the Rust reasoning core wrapper.

These skip cleanly when the library has not been built, so the pure-Python
default install keeps passing ``reasoning/tests`` unchanged.
"""
from __future__ import annotations

import pytest

from reasoning.engine import ReasoningEngine
from reasoning.solver import IpasirStatus

try:
    from reasoning.rust_solver import RustSolver, rust_signature
    _SIGNATURE = rust_signature()
except ImportError as error:
    pytest.skip(f"Rust reasoning core is not built: {error}",
                allow_module_level=True)


def test_signature_reports_cadical() -> None:
    assert _SIGNATURE.startswith("cadical")


def test_propagate_and_fixed() -> None:
    solver = RustSolver([{1}, {-1, 2}], {1, 2}, set())
    assert solver.propagate() is IpasirStatus.SATISFIABLE
    assert solver.fixed(1) == 1
    assert solver.fixed(-1) == -1
    assert solver.fixed(2) == 1
    assert solver.fixed(0) == 0


def test_solve_val_and_bulk_model() -> None:
    solver = RustSolver([{1, 2}], {1, 2})
    assert solver.solve() is IpasirStatus.SATISFIABLE
    assert solver.val(1) in (1, -1)
    assert solver.val(2) in (2, -2)
    assert solver.val(1) > 0 or solver.val(2) > 0
    assert solver.val(0) == 0
    assert solver.val(3) == 0


def test_assumptions_are_temporary() -> None:
    solver = RustSolver([{1, 2}, {-1, -2}], {1, 2})
    solver.assume(1)
    assert solver.solve() is IpasirStatus.SATISFIABLE
    assert solver.val(2) == -2
    assert solver.solve() is IpasirStatus.SATISFIABLE


def test_add_clause_restarts_and_normalizes() -> None:
    solver = RustSolver([{1, 2}], {1, 2})
    assert solver.solve() is IpasirStatus.SATISFIABLE
    solver.add(-1)
    solver.add(0)
    assert solver.solve() is IpasirStatus.SATISFIABLE
    assert solver.val(1) == -1
    tautology = RustSolver([[1, -1, 2]])
    assert tautology.solve() is IpasirStatus.SATISFIABLE
    assert tautology.val(2) != 0


def test_unsatisfiable_solver() -> None:
    solver = RustSolver([{1}, {-1}])
    assert solver.propagate() is IpasirStatus.UNSATISFIABLE
    assert solver.solve() is IpasirStatus.UNSATISFIABLE


def test_copy_is_independent() -> None:
    solver = RustSolver([{1}])
    temporary = solver.copy()
    temporary.clause(-1)
    assert temporary.solve() is IpasirStatus.UNSATISFIABLE
    assert solver.solve() is IpasirStatus.SATISFIABLE


def test_engine_accepts_rust_solver_class() -> None:
    engine = ReasoningEngine([{1, -2}, {2}], RustSolver)
    assert engine.ask(1) is True
    assert ReasoningEngine([{1, -2}, {2}], RustSolver).ask(-1) is False
    assert ReasoningEngine([{1, 2}], RustSolver).ask(1) is None
