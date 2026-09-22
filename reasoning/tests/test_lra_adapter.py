from sympy import I, Q, MatrixSymbol, Rational
from sympy.abc import x, y

import pytest

from reasoning.clauses import ClauseDB, assert_formula
from reasoning.lra_adapter import build_lra_theory, lra_constraints
from reasoning.satask import satask
from reasoning.sympy_adapter import normalize


def _database(expr: object) -> ClauseDB:
    db = ClauseDB()
    assert_formula(normalize(expr), db)
    return db


def _id(db: ClauseDB, expr: object) -> int:
    return db.encoding[normalize(expr)]


def test_relations_are_interpreted_and_constants_become_conflicts() -> None:
    db = _database(Q.gt(x, 1) & Q.lt(2, 3) & Q.eq(x, 2))
    constraints, conflicts = lra_constraints(db)
    assert set(constraints) == {_id(db, Q.gt(x, 1)), _id(db, Q.eq(x, 2))}
    assert conflicts == [[_id(db, Q.lt(2, 3))]]


def test_non_relational_atoms_are_skipped() -> None:
    db = _database(Q.real(x) & Q.positive(y) & Q.ne(x, 0) & Q.gt(x, 0))
    constraints, conflicts = lra_constraints(db)
    assert set(constraints) == {_id(db, Q.gt(x, 0))}
    assert conflicts == []


def test_unhandled_arguments_leave_the_atom_to_the_sat_layer() -> None:
    db = _database(Q.gt(x, 0.5) & Q.lt(I, 1) & Q.gt(x, 0))
    constraints, _ = lra_constraints(db)
    assert set(constraints) == {_id(db, Q.gt(x, 0))}


def test_matrix_relations_are_skipped() -> None:
    matrix = MatrixSymbol("A", 2, 2)
    db = _database(Q.eq(matrix, matrix) & Q.gt(x, 0))
    constraints, conflicts = lra_constraints(db)
    assert set(constraints) == {_id(db, Q.gt(x, 0))}
    assert conflicts == []
    # Q.eq(A, A) is true, but satask has no handler for it; the theory must
    # not mistake the zero-matrix arithmetic for a false equality.
    assert satask(Q.eq(matrix, matrix), use_lra_theory=True) is None


def test_build_lra_theory_returns_no_solver_without_relations() -> None:
    solver, conflicts = build_lra_theory(_database(Q.real(x)))
    assert solver is None
    assert conflicts == []


def test_slack_terms_share_one_variable() -> None:
    db = _database(Q.lt(x + y, 0) & Q.le(x + y, 1))
    solver, _ = build_lra_theory(db)
    assert solver is not None
    assert len(solver.slack_rows) == 1


def test_satask_finds_the_relation_implications() -> None:
    assert satask(Q.le(x, y), Q.gt(x, y), use_lra_theory=True) is False
    assert satask(Q.ge(x, y), Q.lt(x, y), use_lra_theory=True) is False
    assert satask(Q.gt(y, x), Q.lt(x, y), use_lra_theory=True) is True
    assert satask(Q.lt(y, x), Q.gt(x, y), use_lra_theory=True) is True
    assert satask(Q.le(y, x), Q.ge(x, y), use_lra_theory=True) is True


def test_satask_derives_entailment_through_bounds() -> None:
    assert satask(Q.gt(x, 0), Q.gt(x, 1), use_lra_theory=True) is True
    assert satask(Q.gt(x, 1), Q.gt(x, 0), use_lra_theory=True) is None
    assert satask(Q.gt(x, 0), Q.gt(x, 1) & Q.lt(x, 2), use_lra_theory=True) is True
    assert satask(Q.gt(x + y, 0), Q.gt(x, 1) & Q.gt(y, 0),
                  use_lra_theory=True) is True


def test_satask_raises_on_theory_inconsistent_assumptions() -> None:
    with pytest.raises(ValueError, match="Inconsistent assumptions"):
        satask(Q.real(x), Q.gt(x, 1) & Q.lt(x, 0), use_lra_theory=True)
    with pytest.raises(ValueError, match="Inconsistent assumptions"):
        satask(Q.real(x), Q.eq(x, 1) & Q.eq(x, 2), use_lra_theory=True)


def test_satask_handles_constant_relations() -> None:
    assert satask(Q.gt(2, 1), use_lra_theory=True) is True
    assert satask(Q.lt(2, 1), use_lra_theory=True) is False
    assert satask(Q.gt(2, 1)) is None


def test_satask_handles_rational_bounds() -> None:
    assert satask(Q.gt(x, Rational(1, 3)), Q.gt(x, Rational(1, 2)),
                  use_lra_theory=True) is True
    assert satask(Q.gt(x, Rational(1, 2)), Q.gt(3 * x, Rational(3, 2)),
                  use_lra_theory=True) is True


def test_satask_eq_implies_other_relations() -> None:
    assert satask(Q.gt(x, 0), Q.eq(x, 1), use_lra_theory=True) is True
    assert satask(Q.eq(x, 1), Q.eq(x, 1), use_lra_theory=True) is True
    assert satask(Q.lt(x, 0), Q.eq(x, 1), use_lra_theory=True) is False


def test_the_flag_is_required_for_the_theory() -> None:
    assert satask(Q.le(x, y), Q.gt(x, y)) is None
    assert satask(Q.gt(x, 0), Q.gt(x, 1)) is None
    assert satask(Q.gt(2, 1)) is None


def test_unhandled_atoms_do_not_disable_the_rest() -> None:
    # Q.ne is a disjunction, so the theory ignores it but interprets the
    # relation, which still refutes the negated inequality.
    assert satask(Q.gt(x, 0), Q.ne(x, 0) & Q.eq(x, 2),
                  use_lra_theory=True) is True


def test_known_facts_still_apply_in_lra_mode() -> None:
    assert satask(Q.real(x), Q.positive(x), use_lra_theory=True) is True
    assert satask(Q.positive(x), Q.real(x) & Q.negative(x),
                  use_lra_theory=True) is False
