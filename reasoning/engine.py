"""Integer-CNF reasoning API independent of SymPy."""
from __future__ import annotations

from typing import AbstractSet, Iterable, cast

from .solver import IpasirStatus, SATSolver
from .theory import TheorySolver


class ReasoningEngine:
    """Answer whether an integer literal follows from a clause database.

    Theory solvers can be passed in to prune assignments that the clauses
    alone allow; they are used for both the consistency check and every
    query.
    """

    def __init__(self, factbase: object,
                 theory_solvers: Iterable[TheorySolver] = ()) -> None:
        self._factbase = factbase
        clauses = cast("Iterable[Iterable[int]]",
                       getattr(factbase, "data", factbase))
        self._clauses: list[tuple[int, ...]] = [tuple(clause) for clause in clauses]
        variables = cast("AbstractSet[int] | None",
                         getattr(factbase, "variables", None))
        if any(not clause for clause in self._clauses):
            raise ValueError("Inconsistent assumptions")
        if any(literal == 0 for clause in self._clauses for literal in clause):
            raise ValueError("0 is not a CNF literal")
        self._solver = SATSolver(self._clauses, variables, set(),
                                 theory_solvers=theory_solvers)
        if self._solver.propagate() is IpasirStatus.UNSATISFIABLE:
            raise ValueError("Inconsistent assumptions")
        self._model_values: dict[int, int] | None = None

    def _base_model(self) -> dict[int, int]:
        """Return one base model, solving it once and retaining its values.

        The incremental solver clears its model after an assumed solve. The
        cached values let independent queries reuse that base result while the
        solver itself checks only the opposite assumption each time.
        """
        if self._model_values is None:
            if self._solver.solve() is IpasirStatus.UNSATISFIABLE:
                raise ValueError("Inconsistent assumptions")
            self._model_values = {
                variable: self._solver.val(variable)
                for variable in range(1, len(self._solver.variable_set))
            }
        return self._model_values

    def fixed(self, literal: int | bool) -> bool | None:
        if isinstance(literal, bool):
            return literal
        value = self._solver.fixed(literal)
        return {1: True, -1: False, 0: None}[value]

    def ask(self, literal: int | bool, early_return: bool = False) -> bool | None:
        """Return whether *literal* is entailed, contradicted, or unknown.

        ``early_return`` only considers root-level unit propagation. This
        intentionally does not complete the consistency check.
        """
        if isinstance(literal, bool):
            if early_return:
                return literal
            self._base_model()
            return literal
        if literal == 0:
            raise ValueError("0 is not a query literal")
        if early_return:
            propagated = self.fixed(literal)
            if propagated is not None:
                return propagated

        model = self._base_model()
        # The solver reports a variable's model value. Normalise a negative
        # query first, then orient the result back to the queried literal.
        value = model.get(abs(literal), 0)
        if value == 0:
            return None
        self._solver.assume(-value)
        if self._solver.solve() is IpasirStatus.SATISFIABLE:
            return None
        return (value > 0) if literal > 0 else (value < 0)
