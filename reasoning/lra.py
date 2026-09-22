"""A linear real-arithmetic theory solver for the DPLL(T) core.

This is a SymPy-free port of the ``LRASolver`` from SymPy's
``logic.algorithms.lra_theory``, which implements the dual simplex algorithm
of Dutertre and de Moura, "A Fast Linear-Arithmetic Solver for DPLL(T)"
(https://link.springer.com/chapter/10.1007/11817963_11).

The solver is given a mapping from SAT atom ids to constraints of the form

    sum(coefficient * term for term, coefficient in terms) + constant

compared with zero, where ``terms`` are opaque hashable objects, the
coefficients and constant are :class:`fractions.Fraction`, and the comparison
is one of ``<=``, ``<`` and ``==`` (``>=`` and ``>`` are normalized away by
negating).  Since terms are opaque, the core never needs SymPy: the adapter
in :mod:`reasoning.lra_adapter` interprets relation atoms and hands over the
records, and the same solver serves any other linear domain.

The solver implements the four methods of :class:`reasoning.theory.TheorySolver`
(``assert_lit``, ``check``, ``push_level``, ``pop_level``).  It has no theory
propagation and treats distinct terms as independent variables, which is
sound (a relaxation) but can leave nonlinear or term-sharing constraints
undecided.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Any, Hashable, Iterable, Mapping, Sequence, cast

Term = Hashable

# (terms, constant, strict, equality) representing
#
#     sum(coefficient*term for term, coefficient in terms) + constant
#
# compared with zero as ``<=`` when strict is false, ``<`` when strict is
# true and ``==`` when equality is true.
LRAConstraint = tuple[tuple[tuple[Term, Fraction], ...], Fraction, bool, bool]

_RationalValue = Fraction | float


class _Slack:
    """A unique identity for the slack variable of a multi-term expression."""

    __slots__ = ("index",)

    def __init__(self, index: int) -> None:
        self.index = index

    def __repr__(self) -> str:
        return f"slack{self.index}"


class LRARational:
    """A rational number plus or minus an arbitrary small delta."""

    __slots__ = ("value",)

    def __init__(self, rational: _RationalValue, delta: _RationalValue) -> None:
        self.value = (rational, delta)

    @property
    def q(self) -> _RationalValue:
        return self.value[0]

    @property
    def d(self) -> _RationalValue:
        return self.value[1]

    def __lt__(self, other: LRARational) -> bool:
        return self.value < other.value

    def __le__(self, other: LRARational) -> bool:
        return self.value <= other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LRARational) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __add__(self, other: LRARational) -> LRARational:
        return LRARational(self.q + other.q, self.d + other.d)

    def __sub__(self, other: LRARational) -> LRARational:
        return LRARational(self.q - other.q, self.d - other.d)

    def __mul__(self, other: _RationalValue) -> LRARational:
        assert not isinstance(other, LRARational)
        return LRARational(self.q * other, self.d * other)

    def __getitem__(self, index: int) -> Any:
        return self.value[index]

    def __repr__(self) -> str:
        return repr(self.value)


class LRAVariable:
    """The upper and lower bounds known for one term."""

    __slots__ = ("var", "upper", "upper_literal", "lower", "lower_literal",
                 "assign", "col_idx")

    def __init__(self, var: Term) -> None:
        self.initialize()
        self.var = var
        self.col_idx: int | None = None

    def initialize(self) -> None:
        self.upper = LRARational(math.inf, 0)
        self.upper_literal: int | None = None
        self.lower = LRARational(-math.inf, 0)
        self.lower_literal: int | None = None
        self.assign = LRARational(Fraction(0), 0)

    def __repr__(self) -> str:
        return repr(self.var)

    def set_bound(self, boundary: Boundary, literal: int) -> None:
        """Set the upper or lower bound and record the literal that set it."""
        is_negated = literal < 0
        ci, upper = boundary.to_rational(is_negated)
        if upper:
            self.upper = ci
            self.upper_literal = literal
        else:
            self.lower = ci
            self.lower_literal = literal

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LRAVariable) and other.var == self.var

    def __hash__(self) -> int:
        return hash(self.var)


class Boundary:
    """An upper or lower bound on a term."""

    __slots__ = ("var", "bound", "strict", "upper")

    def __init__(self, var: LRAVariable, bound: _RationalValue,
                 upper: bool, strict: bool) -> None:
        self.var = var
        self.bound = bound
        self.strict = strict
        self.upper = upper

    def to_rational(self, is_negated: bool) -> tuple[LRARational, bool]:
        """Return the effective bound and direction, honoring negation."""
        upper = self.upper != is_negated
        delta = 0
        if self.strict != is_negated:
            delta = -1 if upper else 1
        return LRARational(self.bound, delta), upper

    def __repr__(self) -> str:
        relation = "<" if self.strict else "<="
        if not self.upper:
            relation = ">" if self.strict else ">="
        return f"({self.var.var} {relation} {self.bound})"

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Boundary)
                and (self.var, self.bound, self.strict, self.upper)
                == (other.var, other.bound, other.strict, other.upper))

    def __hash__(self) -> int:
        return hash((self.var, self.bound, self.strict, self.upper))


class BoundLevel:
    """Bound updates made during one SAT decision level, with undo data."""

    __slots__ = ("updates",)

    def __init__(self) -> None:
        self.updates: list[
            tuple[LRAVariable, LRARational, int | None, bool]
        ] = []

    def record(self, var: LRAVariable, upper: bool) -> None:
        if upper:
            self.updates.append((var, var.upper, var.upper_literal, upper))
        else:
            self.updates.append((var, var.lower, var.lower_literal, upper))

    def undo(self) -> None:
        var, bound, literal, upper = self.updates.pop()
        if upper:
            var.upper, var.upper_literal = bound, literal
        else:
            var.lower, var.lower_literal = bound, literal


_Matrix = list[list[Fraction]]


def _rref(matrix: _Matrix) -> tuple[_Matrix, list[int]]:
    """Return the reduced row echelon form and its pivot columns.

    This is the small rational equivalent of the SymPy ``Matrix.rref`` call
    in the upstream implementation, with rows and columns indexed the same
    way.  Elimination goes left to right and the first nonzero entry of a
    pivot row is normalized to one.
    """
    A = [row[:] for row in matrix]
    if not A:
        return A, []
    ncols = len(A[0])
    pivots: list[int] = []
    pivot_row = 0
    for col in range(ncols):
        pivot = next((r for r in range(pivot_row, len(A)) if A[r][col] != 0),
                     None)
        if pivot is None:
            continue
        A[pivot_row], A[pivot] = A[pivot], A[pivot_row]
        inverse = A[pivot_row][col]
        A[pivot_row] = [value / inverse for value in A[pivot_row]]
        for r in range(len(A)):
            if r != pivot_row and A[r][col] != 0:
                factor = A[r][col]
                A[r] = [value - factor * pivot_value
                        for value, pivot_value in zip(A[r], A[pivot_row])]
        pivots.append(col)
        pivot_row += 1
        if pivot_row == len(A):
            break
    return A, pivots


def _build_tableau(rows: Sequence[tuple[tuple[tuple[Term, Fraction], ...], Term]],
                   variables: Sequence[Term]) -> _Matrix:
    """Build the tableau, one row ``sum(coeff*var) - slack = 0`` per slack."""
    A = [[Fraction(0)] * len(variables) for _ in rows]
    column = {variable: index for index, variable in enumerate(variables)}
    for row, (terms, slack) in enumerate(rows):
        for variable, coefficient in terms:
            A[row][column[variable]] += coefficient
        A[row][column[slack]] = Fraction(-1)
    return A


def _reduce_matrix(A: _Matrix, basic: list[Term], nonbasic: list[Term],
                   nonatom_vars: set[Term], testing_mode: bool) -> tuple[
                       _Matrix, list[Term], list[Term]]:
    """Eliminate every non-atom variable from the tableau.

    All non-atom variables are dependent on the atom variables, so an
    assignment for the atom variables can always be extended to them.  The
    Gaussian elimination removes their columns from the tableau, turning
    some basic variables into nonbasic ones as a side effect.
    """
    if not nonatom_vars:
        return A, basic, nonbasic
    if testing_mode:
        # Precondition of every tableau: its trailing square block is -I.
        m = len(basic)
        n = len(nonbasic) + len(basic)
        for r, row in enumerate(A):
            for c, value in enumerate(row[n - m:]):
                expected = Fraction(-1) if r == c else Fraction(0)
                assert value == expected, "tableau is not in the -I convention"

    kept_nonbasic = [v for v in nonbasic if v not in nonatom_vars]
    # Non-atom columns come first so rref pivots on them before touching the
    # kept nonbasic variables or the existing basic block.
    sorted_col_order = (sorted(nonatom_vars, key=repr) + list(basic)
                        + kept_nonbasic)
    var_to_col_orig = {v: i for i, v in enumerate(list(nonbasic) + list(basic))}
    A = [[row[var_to_col_orig[v]] for v in sorted_col_order] for row in A]

    B, pivots = _rref(A)

    keep_rows = [r for r, pivot_col in enumerate(pivots)
                 if pivot_col >= len(nonatom_vars)]
    new_basic = [sorted_col_order[pivots[r]] for r in keep_rows]
    basic_set = set(new_basic)
    new_nonbasic = [v for v in kept_nonbasic + list(basic) if v not in basic_set]

    var_to_col_sorted = {v: i for i, v in enumerate(sorted_col_order)}
    # rref leaves a 1 on each pivot; the convention here is -1.
    A = [[-B[r][var_to_col_sorted[v]] for v in new_nonbasic + new_basic]
         for r in keep_rows]
    if testing_mode:
        assert set(nonatom_vars).isdisjoint(new_basic + new_nonbasic)
        assert set(new_basic) <= set(basic)
        assert set(new_nonbasic) <= set(kept_nonbasic) | set(basic)
    return A, new_basic, new_nonbasic


class LRASolver:
    """Dual simplex theory solver over opaque linear terms.

    Build one with :meth:`from_constraints` rather than the constructor.
    """

    def __init__(self, A: _Matrix, basic: list[LRAVariable],
                 nonbasic: list[LRAVariable],
                 atom_id_to_boundaries: dict[int, list[Boundary]],
                 slack_rows: list[tuple[tuple[tuple[Term, Fraction], ...], Term]],
                 testing_mode: bool = False) -> None:
        self.run_checks = testing_mode
        self.slack_rows = slack_rows
        self.atom_id_to_boundaries = atom_id_to_boundaries
        self.A = A
        self._A0 = [row[:] for row in A] if testing_mode else None
        # Basic and nonbasic variables can swap places while pivoting; the
        # underlying set of variables cannot.
        self.basic = basic
        self.nonbasic = set(nonbasic)
        self.all_var = list(nonbasic) + list(basic)
        self.bound_history = [BoundLevel()]

    @staticmethod
    def from_constraints(
            constraints: Mapping[int, LRAConstraint],
            testing_mode: bool = False) -> LRASolver:
        """Build a solver from atom id to constraint records."""
        atom_id_to_boundaries: dict[int, list[Boundary]] = {}
        slack_rows: list[
            tuple[tuple[tuple[Term, Fraction], ...], Term]
        ] = []
        slack_of: dict[tuple[tuple[Term, Fraction], ...], Term] = {}
        basic: list[Term] = []
        nonbasic: list[Term] = []
        atom_vars: set[Term] = set()
        var_to_lra_var: dict[Term, LRAVariable] = {}

        for literal, (terms, constant, strict, equality) in constraints.items():
            for variable, _ in terms:
                if variable not in var_to_lra_var:
                    var_to_lra_var[variable] = LRAVariable(variable)
                    nonbasic.append(variable)

            if len(terms) == 1:
                variable, coefficient = terms[0]
            else:
                if terms not in slack_of:
                    slack: Term = _Slack(len(slack_rows) + 1)
                    var_to_lra_var[slack] = LRAVariable(slack)
                    basic.append(slack)
                    slack_of[terms] = slack
                    slack_rows.append((terms, slack))
                variable = slack_of[terms]
                coefficient = Fraction(1)

            atom_vars.add(variable)
            assert coefficient != 0

            bound = -constant / coefficient
            var = var_to_lra_var[variable]
            if equality:
                b1 = Boundary(var, bound, True, False)
                b2 = Boundary(var, bound, False, False)
                atom_id_to_boundaries[literal] = [b1, b2]
            else:
                upper = coefficient > 0
                atom_id_to_boundaries[literal] = [
                    Boundary(var, bound, upper, strict)]

        A = _build_tableau(slack_rows, nonbasic + basic)
        nonatom_vars = {variable for variable in nonbasic
                        if variable not in atom_vars}
        A, basic, nonbasic = _reduce_matrix(
            A, basic, nonbasic, nonatom_vars, testing_mode)
        nonbasic_vars = [var_to_lra_var[v] for v in nonbasic]
        basic_vars = [var_to_lra_var[v] for v in basic]
        for index, var in enumerate(nonbasic_vars + basic_vars):
            var.col_idx = index
        return LRASolver(A, basic_vars, nonbasic_vars, atom_id_to_boundaries,
                         slack_rows, testing_mode)

    def reset(self) -> None:
        """Forget every bound asserted so far."""
        for var in self.all_var:
            var.initialize()
        self.bound_history = [BoundLevel()]

    def assert_lit(self, literal: int) -> tuple[bool, list[int]] | None:
        """Record an assigned literal and return a conflict clause if any."""
        if abs(literal) not in self.atom_id_to_boundaries:
            return None

        boundaries = self.atom_id_to_boundaries[abs(literal)]
        if len(boundaries) > 1 and literal < 0:
            # A negated equality is a disjunction and cannot be a bound.
            return None

        result: tuple[bool, list[int]] | None = None
        for boundary in boundaries:
            result = self._assert_bound(boundary, literal)
            if result is not None and not result[0]:
                break
        return result

    def _assert_bound(self, boundary: Boundary, literal: int) -> tuple[
            bool, list[int]] | None:
        xi = boundary.var
        ci, upper = boundary.to_rational(is_negated=literal < 0)

        sign = 1 if upper else -1
        target_bound = xi.upper if upper else xi.lower
        opposing_bound = xi.lower if upper else xi.upper
        conflicting_lit = xi.lower_literal if upper else xi.upper_literal

        # Normalize a lower bound to the equivalent upper bound situation.
        c_norm = ci * sign
        target_norm = target_bound * sign
        opposing_norm = opposing_bound * sign

        if c_norm >= target_norm:
            return None
        if c_norm < opposing_norm:
            assert conflicting_lit is not None
            return False, [-conflicting_lit, -literal]

        self.bound_history[-1].record(xi, upper)
        xi.set_bound(boundary, literal)

        if xi in self.nonbasic and xi.assign * sign > c_norm:
            self._update(xi, ci)

        if self.run_checks and all(not math.isinf(var.assign.q)
                                   for var in self.all_var):
            values = [cast(Fraction, var.assign.q) for var in self.all_var]
            assert self._A0 is not None
            for row in self._A0:
                total = sum((a * x for a, x in zip(row, values)), Fraction(0))
                assert abs(total) < Fraction(1, 10 ** 10)

        return None

    def _update(self, xi: LRAVariable, value: LRARational) -> None:
        """Keep every basic equation true while nonbasic *xi* moves to *value*."""
        index = xi.col_idx
        assert index is not None
        delta = value - xi.assign
        for j, b in enumerate(self.basic):
            a_ji = self.A[j][index]
            b.assign = b.assign + delta * a_ji
        xi.assign = value

    def check(self) -> tuple[bool, Any]:
        """Return ``(True, assignment)`` or ``(False, conflict clause)``."""
        while True:
            if self.run_checks:
                for nb in self.nonbasic:
                    assert (nb.assign >= nb.lower) is True
                    assert (nb.assign <= nb.upper) is True
                assert all(var.upper.d <= 0 for var in self.all_var)
                assert all(var.lower.d >= 0 for var in self.all_var)

            cand = [(r, b) for r, b in enumerate(self.basic)
                    if b.assign < b.lower or b.assign > b.upper]
            if not cand:
                return True, {var: var.assign for var in self.all_var}
            i, xi = min(cand, key=lambda item: cast(int, item[1].col_idx))

            if xi.assign < xi.lower:
                incoming = [nb for nb in self.nonbasic
                            if (self.A[i][cast(int, nb.col_idx)] > 0
                                and nb.assign < nb.upper)
                            or (self.A[i][cast(int, nb.col_idx)] < 0
                                and nb.assign > nb.lower)]
                if len(incoming) == 0:
                    return False, self._conflict(i, xi, lower=True)
                xj = min(incoming, key=lambda var: repr(var.var))
                self._pivot_and_update(i, xi, xj, xi.lower)

            if xi.assign > xi.upper:
                incoming = [nb for nb in self.nonbasic
                            if (self.A[i][cast(int, nb.col_idx)] < 0
                                and nb.assign < nb.upper)
                            or (self.A[i][cast(int, nb.col_idx)] > 0
                                and nb.assign > nb.lower)]
                if len(incoming) == 0:
                    return False, self._conflict(i, xi, lower=False)
                xj = min(incoming, key=lambda var: cast(int, var.col_idx))
                self._pivot_and_update(i, xi, xj, xi.upper)

    def _conflict(self, i: int, xi: LRAVariable, lower: bool) -> list[int]:
        """Explain why basic variable *xi* cannot satisfy its bounds.

        Exactly one of the two ``check`` branches calls this: the bounds of
        the nonbasic variables that could move *xi* back inside are the
        explanation.
        """
        N_plus = [nb for nb in self.nonbasic if self.A[i][cast(int, nb.col_idx)] > 0]
        N_minus = [nb for nb in self.nonbasic if self.A[i][cast(int, nb.col_idx)] < 0]
        bounds: list[int | None] = []
        if lower:
            bounds = ([nb.upper_literal for nb in N_plus]
                      + [nb.lower_literal for nb in N_minus]
                      + [xi.lower_literal])
        else:
            bounds = ([nb.upper_literal for nb in N_minus]
                      + [nb.lower_literal for nb in N_plus]
                      + [xi.upper_literal])
        assert all(bound is not None for bound in bounds)
        return [-cast(int, bound) for bound in bounds]

    def _pivot_and_update(self, i: int, xi: LRAVariable, xj: LRAVariable,
                          value: LRARational) -> None:
        """Pivot *xi* with nonbasic *xj* and adjust assignments accordingly."""
        j = xj.col_idx
        assert j is not None
        assert self.A[i][j] != 0
        theta = (value - xi.assign) * (1 / self.A[i][j])
        xi.assign = value
        xj.assign = xj.assign + theta
        for k in range(len(self.basic)):
            if k != i:
                self.basic[k].assign = (self.basic[k].assign
                                        + theta * self.A[k][j])
        self._pivot(i, j)
        self.basic[i] = xj
        self.nonbasic.discard(xj)
        self.nonbasic.add(xi)

    def _pivot(self, i: int, j: int) -> None:
        """Pivot the tableau about entry ``A[i][j]``."""
        Aij = self.A[i][j]
        if Aij == 0:
            raise ZeroDivisionError("Tried to pivot about zero-valued entry.")
        self.A[i] = [-value / Aij for value in self.A[i]]
        for row in range(len(self.A)):
            if row != i and self.A[row][j] != 0:
                factor = self.A[row][j]
                self.A[row] = [value + factor * pivot_value
                               for value, pivot_value in zip(self.A[row],
                                                             self.A[i])]

    def backtrack(self) -> None:
        """Undo the most recent bound update."""
        if not self.bound_history[-1].updates:
            raise ValueError("Cannot backtrack, bound_history stack is empty")
        self.bound_history[-1].undo()

    def push_level(self) -> None:
        """Save the current state for the matching :meth:`pop_level`."""
        self.bound_history.append(BoundLevel())

    def pop_level(self) -> None:
        """Undo every bound asserted since the matching :meth:`push_level`."""
        while self.bound_history[-1].updates:
            self.backtrack()
        self.bound_history.pop()


__all__ = [
    "Boundary", "BoundLevel", "LRAConstraint", "LRARational", "LRASolver",
    "LRAVariable",
]
