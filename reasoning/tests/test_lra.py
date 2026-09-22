from fractions import Fraction

import pytest

from reasoning.lra import (
    Boundary, LRARational, LRASolver, LRAVariable, _reduce_matrix,
)

F = Fraction


def _single(term: object, coefficient: Fraction, constant: Fraction,
            strict: bool = False,
            equality: bool = False) -> tuple[tuple[tuple[object, Fraction], ...],
                                             Fraction, bool, bool]:
    return ((term, coefficient),), constant, strict, equality


def _linear(terms: dict[object, Fraction], constant: Fraction = F(0),
            strict: bool = False,
            equality: bool = False) -> tuple[tuple[tuple[object, Fraction], ...],
                                             Fraction, bool, bool]:
    return tuple(terms.items()), constant, strict, equality


def _value(solver: LRASolver, term: object) -> LRARational:
    for var in solver.all_var:
        if var.var == term:
            return var.assign
    raise KeyError(term)


def test_conflicting_bounds_are_reported_with_their_literals() -> None:
    solver = LRASolver.from_constraints({
        1: _single("x", F(1), F(0)),
        2: _single("x", F(-1), F(1)),
    })
    assert solver.assert_lit(1) is None
    result = solver.assert_lit(2)
    assert result is not None and result[0] is False
    assert sorted(result[1]) == [-2, -1]


def test_conflict_clause_negates_the_asserted_literals() -> None:
    constraints = {
        1: _single("x", F(1), F(0)),
        2: _single("x", F(-1), F(1)),
    }
    solver = LRASolver.from_constraints(constraints)
    solver.assert_lit(2)
    result = solver.assert_lit(1)
    assert result == (False, [-2, -1])
    # The same conflict found in the other direction names the same bounds.
    solver = LRASolver.from_constraints(constraints)
    solver.assert_lit(1)
    result = solver.assert_lit(2)
    assert result == (False, [-1, -2])


def test_negated_literal_is_the_opposite_bound() -> None:
    solver = LRASolver.from_constraints({1: _single("x", F(1), F(0))})
    # 1 is x <= 0; its negation is x > 0, which is consistent by itself.
    assert solver.assert_lit(-1) is None
    assert solver.check()[0] is True
    # And x <= 0 together with x > 0 is not.
    assert solver.assert_lit(1) == (False, [1, -1])


def test_equality_is_satisfied_at_its_bound() -> None:
    solver = LRASolver.from_constraints({1: _single("x", F(1), F(-3), equality=True)})
    assert solver.assert_lit(1) is None
    sat, assignment = solver.check()
    assert sat is True
    assert _value(solver, "x").q == 3


def test_negated_equality_is_left_unconstrained() -> None:
    solver = LRASolver.from_constraints({1: _single("x", F(1), F(-3), equality=True)})
    assert solver.assert_lit(-1) is None
    assert solver.check()[0] is True


def test_slack_variables_carry_multi_term_constraints() -> None:
    solver = LRASolver.from_constraints({
        1: _linear({"x": F(1), "y": F(1)}, F(0)),
        2: _single("x", F(-1), F(1)),
        3: _single("y", F(-1), F(1)),
    })
    assert solver.assert_lit(2) is None
    assert solver.assert_lit(3) is None
    assert solver.assert_lit(1) is None
    # The tableau is only known to be infeasible once it is checked.
    sat, conflict = solver.check()
    assert sat is False
    assert sorted(conflict) == [-3, -2, -1]


def test_transitive_entailment_through_a_slack_variable() -> None:
    # x >= 4 and x + y <= 1 require y <= -3.
    solver = LRASolver.from_constraints({
        1: _single("x", F(-1), F(4)),
        2: _linear({"x": F(1), "y": F(1)}, F(-1)),
        3: _single("y", F(-1), F(-2)),
    })
    assert solver.assert_lit(1) is None
    assert solver.assert_lit(2) is None
    # y >= -2 is contradicted by the y <= -3 that x >= 4 and x + y <= 1 force;
    # the conflict can surface during the assertion or during check().
    from_assertion = solver.assert_lit(3)
    if from_assertion is None:
        assert solver.check()[0] is False
    else:
        assert from_assertion[0] is False


def test_push_and_pop_restore_bounds() -> None:
    solver = LRASolver.from_constraints({
        1: _single("x", F(1), F(0)),
        2: _single("x", F(-1), F(1)),
    })
    assert solver.assert_lit(1) is None
    assert solver.check()[0] is True
    solver.push_level()
    assert solver.assert_lit(2) is not None
    solver.pop_level()
    assert solver.check()[0] is True
    solver.push_level()
    solver.pop_level()
    assert solver.check()[0] is True


def test_pop_level_undoes_several_bounds() -> None:
    solver = LRASolver.from_constraints({
        1: _single("x", F(-1), F(0)),   # x >= 0
        2: _single("y", F(-1), F(0)),   # y >= 0
        3: _linear({"x": F(1), "y": F(1)}, F(0)),  # x + y <= 0
    })
    solver.push_level()
    assert solver.assert_lit(1) is None
    assert solver.assert_lit(2) is None
    assert solver.assert_lit(3) is None
    assert solver.check()[0] is True
    solver.pop_level()
    assert solver.check()[0] is True


def test_backtrack_without_updates_is_an_error() -> None:
    solver = LRASolver.from_constraints({1: _single("x", F(1), F(0))})
    with pytest.raises(ValueError):
        solver.backtrack()


def test_reset_forgets_every_bound() -> None:
    solver = LRASolver.from_constraints({
        1: _single("x", F(-1), F(1)),
    })
    assert solver.assert_lit(1) is None
    solver.reset()
    assert solver.check()[0] is True


def test_uninterpreted_literals_are_ignored() -> None:
    solver = LRASolver.from_constraints({1: _single("x", F(1), F(0))})
    assert solver.assert_lit(7) is None
    assert solver.assert_lit(-7) is None
    assert solver.check()[0] is True


def test_solver_returns_an_assignment_satisfying_all_bounds() -> None:
    constraints = {
        1: _linear({"x": F(1), "y": F(1)}, F(-5)),  # x + y <= 5
        2: _single("x", F(-1), F(0)),               # x >= 0
        3: _single("y", F(-1), F(0)),               # y >= 0
    }
    solver = LRASolver.from_constraints(constraints)
    for literal in constraints:
        assert solver.assert_lit(literal) is None
    sat, assignment = solver.check()
    assert sat is True
    upper = _value(solver, "x").q + _value(solver, "y").q
    assert upper <= 5


def test_assignment_respects_delta_bounds() -> None:
    # x < 1 and x > 0 can both hold; x == 1 must not be the assignment.
    solver = LRASolver.from_constraints({
        1: _single("x", F(1), F(-1), strict=True),   # x < 1
        2: _single("x", F(-1), F(0), strict=True),   # x > 0
    })
    assert solver.assert_lit(1) is None
    assert solver.assert_lit(2) is None
    sat, assignment = solver.check()
    assert sat is True
    value = _value(solver, "x")
    assert value < LRARational(F(1), 0)
    assert value > LRARational(F(0), 0)


def test_rational_coefficients_are_preserved() -> None:
    # (1/2)x <= 1 and (1/2)x >= 3 conflict.
    solver = LRASolver.from_constraints({
        1: _single("x", F(1, 2), F(-1)),
        2: _single("x", F(-1, 2), F(3)),
    })
    assert solver.assert_lit(1) is None
    result = solver.assert_lit(2)
    assert result is not None and result[0] is False


def test_testing_mode_checks_internal_invariants() -> None:
    solver = LRASolver.from_constraints({
        1: _linear({"x": F(1), "y": F(1)}, F(-5)),
        2: _single("x", F(-1), F(0)),
        3: _single("y", F(-1), F(0)),
    }, testing_mode=True)
    for literal in (1, 2, 3):
        assert solver.assert_lit(literal) is None
    assert solver.check()[0] is True


def test_reduce_matrix_eliminates_nonatom_columns() -> None:
    # Two rows x + y - s1 = 0 and z + y - s2 = 0 eliminate y.
    A = [
        [F(1), F(1), F(0), F(-1), F(0)],
        [F(0), F(1), F(1), F(0), F(-1)],
    ]
    reduced, basic, nonbasic = _reduce_matrix(
        A, ["s1", "s2"], ["x", "y", "z"], {"y"}, testing_mode=False)
    assert basic == ["s1"]
    assert nonbasic == ["x", "z", "s2"]
    assert len(reduced) == 1


def test_reduce_matrix_collapses_when_every_column_is_eliminated() -> None:
    A = [
        [F(1), F(1), F(0), F(-1), F(0)],
        [F(1), F(2), F(-1), F(0), F(-1)],
    ]
    reduced, basic, nonbasic = _reduce_matrix(
        A, ["s1", "s2"], ["x", "y", "z"], {"y", "z"}, testing_mode=False)
    assert basic == []
    assert reduced == []


@pytest.mark.parametrize("terms,constant,strict,equality", [
    ({"x": F(1)}, F(0), False, False),
    ({"x": F(-1)}, F(1), True, False),
    ({"x": F(1), "y": F(-1)}, F(2), False, False),
    ({"x": F(1, 3)}, F(-2, 5), True, False),
])
def test_every_literal_gets_a_boundary_at_its_normalized_bound(
        terms: dict[object, Fraction], constant: Fraction, strict: bool,
        equality: bool) -> None:
    solver = LRASolver.from_constraints(
        {1: (tuple(terms.items()), constant, strict, equality)})
    boundaries = solver.atom_id_to_boundaries[1]
    assert len(boundaries) == (2 if equality else 1)
    if len(terms) == 1:
        ((_, coefficient),) = terms.items()
        expected = -constant / coefficient
    else:
        expected = -constant
    for boundary in boundaries:
        assert boundary.strict == (strict and not equality)
        assert boundary.bound == expected


def test_slack_rows_record_the_multi_term_expressions() -> None:
    solver = LRASolver.from_constraints({
        1: _linear({"x": F(1), "y": F(1)}, F(0)),
        2: _linear({"x": F(1), "y": F(1)}, F(0)),
    })
    assert len(solver.slack_rows) == 1
    terms, slack = solver.slack_rows[0]
    assert tuple(term for term, _ in terms) == ("x", "y")
    assert slack == solver.atom_id_to_boundaries[1][0].var.var


def test_boundary_and_variable_identity() -> None:
    var = LRAVariable("x")
    assert var == LRAVariable("x")
    assert hash(var) == hash(LRAVariable("x"))
    boundary = Boundary(var, F(1), True, False)
    assert boundary == Boundary(var, F(1), True, False)
    assert hash(boundary) == hash(Boundary(var, F(1), True, False))
    other = Boundary(var, F(2), True, False)
    assert boundary != other


_PROTOCOL_CASES: list[dict[int, tuple[
    tuple[tuple[object, Fraction], ...], Fraction, bool, bool]]] = [
    {
        1: _single("x", F(1), F(-2)),
        2: _single("x", F(-1), F(0)),
        3: _single("y", F(1), F(1)),
    },
    {
        1: _linear({"x": F(1), "y": F(1)}, F(-3)),
        2: _single("x", F(-1), F(0)),
        3: _single("y", F(-1), F(0)),
    },
    {
        1: _single("x", F(1), F(0), equality=True),
        2: _single("x", F(-1), F(0)),
    },
]


@pytest.mark.parametrize("constraints", _PROTOCOL_CASES)
def test_conflicts_only_blame_asserted_literals(
        constraints: dict[int, tuple[
            tuple[tuple[object, Fraction], ...], Fraction, bool, bool]]) -> None:
    for chosen in (1, -1):
        solver = LRASolver.from_constraints(constraints)
        solver.push_level()
        asserted: set[int] = set()
        for literal in sorted(constraints):
            signed = literal * chosen
            result = solver.assert_lit(signed)
            if result is not None and not result[0]:
                assert result[1], "conflict clause must not be empty"
                assert {-item for item in result[1]} <= asserted | {signed}
            asserted.add(signed)
        solver.pop_level()


@pytest.mark.parametrize("constraints", _PROTOCOL_CASES)
def test_sat_assignment_satisfies_every_held_bound(
        constraints: dict[int, tuple[
            tuple[tuple[object, Fraction], ...], Fraction, bool, bool]]) -> None:
    solver = LRASolver.from_constraints(constraints, testing_mode=True)
    for literal in constraints:
        assert solver.assert_lit(literal) is None
    sat, assignment = solver.check()
    assert sat is True
    for boundaries in solver.atom_id_to_boundaries.values():
        for boundary in boundaries:
            value = assignment[boundary.var]
            if boundary.upper:
                assert value <= LRARational(boundary.bound, 0)
            else:
                assert value >= LRARational(boundary.bound, 0)
