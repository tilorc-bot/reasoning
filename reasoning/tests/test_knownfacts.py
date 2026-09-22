"""The vendored known-fact table must match the installed SymPy.

``tools/regen_known_facts.py`` vendors the ``ask_generated`` templates into
:mod:`reasoning.knownfacts` so the core never imports SymPy.  These tests
recompute the tables from SymPy and compare them as sets, because the SymPy
fact containers are unordered; the checked-in file is canonical.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from sympy.assumptions.ask_generated import (
    get_all_known_matrix_facts, get_all_known_number_facts,
)

from reasoning import knownfacts

REPO_ROOT = Path(__file__).resolve().parents[2]

_CHILD = r"""
import sys


class _BlockSympy:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "sympy" or fullname.startswith("sympy."):
            raise ImportError(f"sympy is blocked: {fullname}")
        return None


sys.meta_path.insert(0, _BlockSympy())

from reasoning import knownfacts

assert len(knownfacts.NUMBER_PREDICATES) == 31
assert len(knownfacts.NUMBER_CLAUSES) == 81
assert len(knownfacts.MATRIX_PREDICATES) == 17
assert len(knownfacts.MATRIX_CLAUSES) == 24
names, clauses = knownfacts.template(True, True)
assert len(names) == 48
assert len(clauses) == 105
assert knownfacts.template(False, False) == ((), ())
assert knownfacts.template(True, False) == (
    knownfacts.NUMBER_PREDICATES, knownfacts.NUMBER_CLAUSES)
assert knownfacts.template(False, True) == (
    knownfacts.MATRIX_PREDICATES, knownfacts.MATRIX_CLAUSES)
assert not any(name == "sympy" or name.startswith("sympy.")
               for name in sys.modules)
"""


def _canonical(facts: Iterable[Any]) -> tuple[
        tuple[str, ...], frozenset[tuple[int, ...]]]:
    names = tuple(sorted({literal.lit.name
                          for clause in facts for literal in clause}))
    encoding = {name: index + 1 for index, name in enumerate(names)}
    clauses = frozenset(
        tuple(sorted(-encoding[literal.lit.name] if literal.is_Not
                     else encoding[literal.lit.name] for literal in clause))
        for clause in facts
    )
    return names, clauses


def test_number_table_matches_sympy() -> None:
    names, clauses = _canonical(get_all_known_number_facts())
    assert names == knownfacts.NUMBER_PREDICATES
    assert clauses == frozenset(knownfacts.NUMBER_CLAUSES)
    assert len(names) == 31
    assert len(clauses) == 81


def test_matrix_table_matches_sympy() -> None:
    names, clauses = _canonical(get_all_known_matrix_facts())
    assert names == knownfacts.MATRIX_PREDICATES
    assert clauses == frozenset(knownfacts.MATRIX_CLAUSES)
    assert len(names) == 17
    assert len(clauses) == 24


def test_merged_template_matches_sympy() -> None:
    number = list(get_all_known_number_facts())
    matrix = list(get_all_known_matrix_facts())
    names, clauses = _canonical(number + matrix)
    assert names == tuple(sorted(knownfacts.NUMBER_PREDICATES
                                 + knownfacts.MATRIX_PREDICATES))
    assert knownfacts.template(True, True) == (names, tuple(sorted(clauses)))
    assert knownfacts.template(False, False) == ((), ())
    assert knownfacts.template(True, False) == (
        knownfacts.NUMBER_PREDICATES, knownfacts.NUMBER_CLAUSES)
    assert knownfacts.template(False, True) == (
        knownfacts.MATRIX_PREDICATES, knownfacts.MATRIX_CLAUSES)


def test_checked_in_tables_are_canonical() -> None:
    for clauses in (knownfacts.NUMBER_CLAUSES, knownfacts.MATRIX_CLAUSES):
        assert list(clauses) == sorted(clauses)
        assert all(list(clause) == sorted(clause) for clause in clauses)


def test_tables_are_reachable_without_sympy() -> None:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + (os.pathsep + existing if existing else ""))
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
