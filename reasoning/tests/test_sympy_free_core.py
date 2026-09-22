"""Guard the boundary between the SymPy-free core and the SymPy adapters.

The core modules must import and work in a fresh interpreter where importing
``sympy`` fails outright.  A stray SymPy import anywhere in that set fails
this test, even when it happens indirectly through a helper.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_CHILD = r"""
import os
import sys

_REPO_ROOT = sys.argv[1]


class _BlockSympy:
    # Refuse any attempt to import sympy or one of its submodules.

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "sympy" or fullname.startswith("sympy."):
            raise ImportError(
                f"sympy is blocked in this interpreter: {fullname}")
        return None


sys.meta_path.insert(0, _BlockSympy())

import reasoning

assert reasoning.__file__.startswith(_REPO_ROOT + os.sep), reasoning.__file__

# Prove the block is active; the real modules below must not need sympy.
try:
    import sympy
except ImportError:
    pass
else:
    raise AssertionError("the sympy import block is not active")

from fractions import Fraction

from reasoning.clauses import ClauseDB, IMPLIES, assert_formula, compile_formula
from reasoning.engine import ReasoningEngine
from reasoning.lra import LRASolver
from reasoning.predicates import Q
from reasoning.solver import IpasirStatus, SATSolver
from reasoning.theory import TheorySolver  # noqa: F401

db = ClauseDB()
assert_formula(IMPLIES("a", "b"), db)
assert_formula("a", db)
query = compile_formula("b", db)
assert ReasoningEngine(db).ask(query) is True

solver = SATSolver([{1}, {-1, 2}], {1, 2})
assert solver.solve() is IpasirStatus.SATISFIABLE
assert solver.val(2) == 2
assert SATSolver([{1}, {-1}], {1}).solve() is IpasirStatus.UNSATISFIABLE

atom = Q.of("real")("x")
assert atom.name == "real"
assert atom.arguments == ("x",)

lra = LRASolver.from_constraints({
    1: (((("x"), Fraction(1)),), Fraction(0), False, False),
    2: (((("x"), Fraction(-1)),), Fraction(1), False, False),
})
assert lra.assert_lit(1) is None
conflict = lra.assert_lit(2)
assert conflict is not None and conflict[0] is False

assert not any(name == "sympy" or name.startswith("sympy.")
               for name in sys.modules)
"""


def _run_child(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + (os.pathsep + existing if existing else ""))
    return subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True)


def test_core_imports_and_solves_without_sympy() -> None:
    completed = _run_child(_CHILD)
    assert completed.returncode == 0, completed.stdout + completed.stderr
