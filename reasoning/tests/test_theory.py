from typing import Any

import pytest

from reasoning.engine import ReasoningEngine
from reasoning.solver import IpasirStatus, SATSolver


class Exclude:
    """A toy theory: two literals may not be true at the same time."""

    def __init__(self, first: int, second: int) -> None:
        self.pair = (first, second)
        self.levels: list[set[int]] = [set()]
        self.pushes = 0
        self.pops = 0

    def assigned(self) -> set[int]:
        assignment: set[int] = set()
        for level in self.levels:
            assignment |= level
        return assignment

    def assert_lit(self, literal: int) -> tuple[bool, list[int]] | None:
        self.levels[-1].add(literal)
        if all(item in self.assigned() for item in self.pair):
            return False, [-item for item in self.pair]
        return None

    def check(self) -> tuple[bool, Any] | None:
        if all(item in self.assigned() for item in self.pair):
            return False, [-item for item in self.pair]
        return True, {}

    def push_level(self) -> None:
        self.pushes += 1
        self.levels.append(set())

    def pop_level(self) -> None:
        self.pops += 1
        self.levels.pop()


def test_theory_prunes_assignments_the_clauses_allow() -> None:
    theory = Exclude(1, 2)
    solver = SATSolver([{1, 2}], {1, 2}, set(), theory_solvers=[theory])
    assert solver.solve() is IpasirStatus.SATISFIABLE
    values = {1: solver.val(1), 2: solver.val(2)}
    assert values[1] != values[2]


def test_theory_conflict_makes_the_formula_unsatisfiable() -> None:
    solver = SATSolver([{1}, {2}], {1, 2}, set(),
                       theory_solvers=[Exclude(1, 2)])
    assert solver.solve() is IpasirStatus.UNSATISFIABLE


def test_theory_conflict_while_asserting_an_assumption_is_not_swallowed() -> None:
    # This is the bug tilorc-bot's review of SymPy #30537 found: a conflict
    # raised while assigning an assumption used to be ignored, so the solver
    # reported SAT for an assignment the theory rejects.
    solver = SATSolver([{1, 2}], {1, 2}, set(),
                       theory_solvers=[Exclude(1, 2)])
    solver.assume(1)
    solver.assume(2)
    assert solver.solve() is IpasirStatus.UNSATISFIABLE


def test_assumptions_are_checked_against_the_theory_too() -> None:
    theory = Exclude(1, 2)
    solver = SATSolver([{1, 2}, {3}], {1, 2, 3}, set(),
                       theory_solvers=[theory])
    solver.assume(1)
    assert solver.solve() is IpasirStatus.SATISFIABLE
    assert solver.val(2) == -2


def test_theory_levels_match_the_solver_levels() -> None:
    theory = Exclude(1, 2)
    solver = SATSolver([{1, 2}], {1, 2}, set(), theory_solvers=[theory])
    assert solver.solve() is IpasirStatus.SATISFIABLE
    # Every level the solver opened was pushed to the theory, and the open
    # levels are exactly the solver's current levels.
    assert theory.pushes == theory.pops + len(solver.levels)
    solver.assume(-1)
    assert solver.solve() is IpasirStatus.SATISFIABLE
    assert theory.pushes == theory.pops + len(solver.levels)


def test_theory_pop_level_undoes_state_with_a_real_backtrack() -> None:
    theory = Exclude(1, 2)
    # Clauses force a decision to be made and unmade before a model exists.
    solver = SATSolver([{1, 2}, {2, 3}, {-3}], {1, 2, 3}, set(),
                       theory_solvers=[theory])
    assert solver.solve() is IpasirStatus.SATISFIABLE
    assert theory.pops > 0


def test_theory_conflict_produces_a_learned_clause() -> None:
    solver = SATSolver([{1, 2}], {1, 2}, set(),
                       theory_solvers=[Exclude(1, 2)])
    assert solver.solve() is IpasirStatus.SATISFIABLE
    assert len(solver.clauses) > 1


class CheckOnly(Exclude):
    """Records literals but only reports conflicts from ``check``."""

    def assert_lit(self, literal: int) -> tuple[bool, list[int]] | None:
        self.levels[-1].add(literal)
        return None


def test_root_theory_conflict_found_at_the_model_check() -> None:
    solver = SATSolver([{1}, {2}], {1, 2}, set(),
                       theory_solvers=[CheckOnly(1, 2)])
    assert solver.solve() is IpasirStatus.UNSATISFIABLE


def test_root_theory_conflict_with_an_assumption_level() -> None:
    solver = SATSolver([{1}, {2}, {5, 6}], {1, 2, 5, 6}, set(),
                       theory_solvers=[CheckOnly(1, 2)])
    solver.assume(5)
    assert solver.solve() is IpasirStatus.UNSATISFIABLE


def test_engine_reports_a_check_only_conflict() -> None:
    engine = ReasoningEngine([{1}, {2}], theory_solvers=[CheckOnly(1, 2)])
    with pytest.raises(ValueError, match="Inconsistent assumptions"):
        engine.ask(1)


def test_duplicate_theory_solvers_are_rejected() -> None:
    theory = Exclude(1, 2)
    with pytest.raises(ValueError, match="Duplicate theory solver"):
        SATSolver([{1, 2}], {1, 2}, set(), theory_solvers=[theory, theory])


def test_theory_solvers_cannot_be_seeded_with_var_settings() -> None:
    with pytest.raises(NotImplementedError):
        SATSolver([{1, 2}], {1, 2}, {1}, theory_solvers=[Exclude(1, 2)])


def test_copy_is_independent_of_the_original_theory() -> None:
    solver = SATSolver([{1, 2}], {1, 2}, set(),
                       theory_solvers=[Exclude(1, 2)])
    copied = solver.copy()
    assert copied.solve() is IpasirStatus.SATISFIABLE
    assert solver.solve() is IpasirStatus.SATISFIABLE
    values = {solver.val(1), solver.val(2)}
    copied_values = {copied.val(1), copied.val(2)}
    assert values == copied_values


def test_engine_reports_inconsistency_found_by_the_theory() -> None:
    with pytest.raises(ValueError, match="Inconsistent assumptions"):
        ReasoningEngine([{1}, {2}], theory_solvers=[Exclude(1, 2)])


def test_engine_answers_queries_under_theory_constraints() -> None:
    # Either 1 or 2 holds; 3 always holds.
    engine = ReasoningEngine([{1, 2}, {3}], theory_solvers=[Exclude(1, 2)])
    assert engine.ask(3) is True
    assert engine.ask(-3) is False
    assert engine.ask(1) is None
    assert engine.ask(2) is None


def test_engine_entails_a_consequence_of_the_theory() -> None:
    # The clauses allow either literal, but the theory forbids 1 together
    # with ~2, so 2 must hold.
    engine = ReasoningEngine([{1, 2}], theory_solvers=[Exclude(1, -2)])
    assert engine.ask(2) is True
    assert engine.ask(-2) is False
    assert engine.ask(1) is None
    assert engine.ask(-1) is None
