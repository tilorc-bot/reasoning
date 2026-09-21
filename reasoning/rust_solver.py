"""Rust reasoning core: a ``SATSolver``-compatible wrapper over CaDiCaL.

The Rust crate in ``rust/`` owns clause normalization, the variable count, the
session state, and every CaDiCaL interaction.  This module only translates the
engine's IPASIR-style calls into a few bulk C ABI crossings:

* clauses are loaded once per formula as one flat, zero-terminated buffer,
* the model is read once per SAT solve with a single ``rcore_model`` call and
  cached for the per-variable ``val()`` calls the engine makes afterwards,
* assumptions and queries stay one call each because there are only a handful.

Build the library with ``cargo build --release`` in ``rust/``.  It is located
with ``$REASONING_CORE_LIB``, else from ``rust/target/release`` or
``rust/target/debug``.  A missing library raises ``ImportError`` when the
solver is first used, so the pure-Python default install keeps working.
"""
from __future__ import annotations

import ctypes
import os
from array import array
from pathlib import Path
from typing import AbstractSet, Iterable, cast

from .solver import IpasirStatus

_LIBRARY_NAMES = (
    "libreasoning_core.so",
    "libreasoning_core.dylib",
    "reasoning_core.dll",
)


def _candidate_libraries() -> list[Path]:
    target = Path(__file__).resolve().parent.parent / "rust" / "target"
    return [target / profile / name
            for profile in ("release", "debug")
            for name in _LIBRARY_NAMES]


def _locate_library() -> Path:
    override = os.environ.get("REASONING_CORE_LIB")
    if override:
        path = Path(override)
        if not path.exists():
            raise ImportError(
                f"REASONING_CORE_LIB points to a missing file: {path}")
        return path
    candidates = _candidate_libraries()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    tried = ", ".join(str(candidate) for candidate in candidates)
    crate = Path(__file__).resolve().parent.parent / "rust"
    raise ImportError(
        "the Rust reasoning core library is not built; run `cargo build "
        f"--release` in {crate} or set REASONING_CORE_LIB (tried: {tried})")


_library: ctypes.CDLL | None = None


def _load_library() -> ctypes.CDLL:
    global _library
    if _library is None:
        path = _locate_library()
        try:
            library = ctypes.CDLL(str(path))
        except OSError as error:
            raise ImportError(
                f"could not load the Rust reasoning core at {path}: {error}"
            ) from error
        library.rcore_signature.restype = ctypes.c_char_p
        library.rcore_new.argtypes = [ctypes.c_int]
        library.rcore_new.restype = ctypes.c_void_p
        library.rcore_free.argtypes = [ctypes.c_void_p]
        library.rcore_add_clauses.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_size_t]
        library.rcore_add_clauses.restype = ctypes.c_int
        for name in ("rcore_propagate", "rcore_solve"):
            function = getattr(library, name)
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_int
        for name in ("rcore_fixed", "rcore_val"):
            function = getattr(library, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_int]
            function.restype = ctypes.c_int
        library.rcore_assume.argtypes = [ctypes.c_void_p, ctypes.c_int]
        library.rcore_model.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_size_t]
        library.rcore_model.restype = ctypes.c_int
        _library = library
    return _library


def rust_signature() -> str:
    """Return the CaDiCaL version string of the loaded Rust core."""
    signature = _load_library().rcore_signature()
    return signature.decode() if signature else ""


class RustSolver:
    """A ``SATSolver``-compatible wrapper around the Rust reasoning core."""

    def __init__(self, clauses: Iterable[Iterable[int]] | None = None,
                 variables: AbstractSet[int] | None = None,
                 var_settings: Iterable[int] = (),
                 heuristic: str = 'vsids', clause_learning: str = 'none',
                 INTERVAL: int = 500) -> None:
        del heuristic, clause_learning, INTERVAL  # CaDiCaL has its own heuristics.
        clause_list: list[Iterable[int]] = list(clauses) if clauses is not None else []
        if variables is not None:
            # The engine always supplies the database's variable set, so the
            # count comes from there instead of a per-literal Python scan.
            maxvar = max(variables, default=0)
        else:
            maxvar = max((abs(lit) for clause in clause_list for lit in clause),
                         default=0)
        self.variable_set: list[bool] = [False] * (maxvar + 1)
        self.var_settings: set[int] = set(var_settings)
        self._clauses: list[Iterable[int]] = clause_list
        self._clause_buffer: list[int] = []
        self._assumptions: list[int] = []
        self._status = IpasirStatus.UNKNOWN
        self._model: list[int] | None = None
        library = _load_library()
        self._solver = library.rcore_new(maxvar)
        if not self._solver:
            raise MemoryError("could not create a Rust reasoning core session")
        if clause_list:
            self._add_clauses(clause_list)

    def _add_clauses(self, clauses: Iterable[Iterable[int]]) -> None:
        """Load clauses as one flat, zero-terminated buffer."""
        flat = array('i')
        for clause in clauses:
            flat.extend(clause)
            flat.append(0)
        if not flat:
            return
        buffer = (ctypes.c_int * len(flat)).from_buffer(flat)
        if not _load_library().rcore_add_clauses(self._solver, buffer, len(flat)):
            raise OSError("the Rust reasoning core rejected a clause buffer")

    def propagate(self) -> IpasirStatus:
        """Propagate at the root level without deciding, like IPASIR propagate."""
        self._status = IpasirStatus(
            _load_library().rcore_propagate(self._solver))
        return self._status

    def fixed(self, lit: int) -> int:
        """Return 1/-1/0 for a root-fixed literal, as IPASIR ``fixed`` does."""
        if lit == 0 or abs(lit) >= len(self.variable_set):
            return 0
        return int(_load_library().rcore_fixed(self._solver, lit))

    def solve(self) -> IpasirStatus:
        """Search under the assumptions collected since the last solve."""
        library = _load_library()
        assumptions, self._assumptions = self._assumptions, []
        for lit in assumptions:
            library.rcore_assume(self._solver, lit)
        self._model = None
        self._status = IpasirStatus(library.rcore_solve(self._solver))
        return self._status

    def val(self, lit: int) -> int:
        """Return the signed model value of *lit*, fetching the whole model once."""
        if self._status is not IpasirStatus.SATISFIABLE:
            raise ValueError("val() is only defined once solve() has returned "
                             "SATISFIABLE.")
        if lit == 0 or abs(lit) >= len(self.variable_set):
            return 0
        if self._model is None:
            count = len(self.variable_set) - 1
            buffer = (ctypes.c_int * count)()
            written = _load_library().rcore_model(self._solver, buffer, count)
            self._model = [int(buffer[index]) for index in range(written)]
        if abs(lit) > len(self._model):
            return 0
        value = self._model[abs(lit) - 1]
        return value if lit > 0 else -value

    def assume(self, lit: int) -> None:
        """Constrain the next ``solve()`` with *lit* without adding a clause."""
        if lit == 0 or abs(lit) >= len(self.variable_set):
            raise ValueError(f"{lit} is not a literal of one of the variables "
                             "the solver was created with.")
        self._assumptions.append(lit)

    def add(self, lit: int) -> None:
        """Add *lit* to the clause being built, or add it when *lit* is 0."""
        if lit != 0:
            if abs(lit) >= len(self.variable_set):
                raise ValueError("%s is not a literal of one of the variables "
                                 "the solver was created with." % lit)
            self._clause_buffer.append(lit)
            return
        clause, self._clause_buffer = self._clause_buffer, []
        self._clauses.append(tuple(clause))
        self._add_clauses([clause])
        self._model = None
        if not clause:
            self._status = IpasirStatus.UNSATISFIABLE
        elif self._status is IpasirStatus.SATISFIABLE:
            self._status = IpasirStatus.UNKNOWN

    def clause(self, *lits: int | Iterable[int]) -> None:
        """Add the clause made up of *lits*, one by one or as one iterable."""
        literals: Iterable[int]
        if len(lits) == 1 and not isinstance(lits[0], int):
            literals = lits[0]
        else:
            literals = cast("tuple[int, ...]", lits)
        for lit in literals:
            self.add(lit)
        self.add(0)

    def copy(self) -> RustSolver:
        """Return a new solver with the same clauses but a fresh search state."""
        return RustSolver(self._clauses, set(range(1, len(self.variable_set))),
                          set())

    def __del__(self) -> None:
        solver = getattr(self, "_solver", None)
        if solver:
            try:
                _load_library().rcore_free(solver)
            except ImportError:
                pass
            self._solver = None


__all__ = ["RustSolver", "rust_signature"]
