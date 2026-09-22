"""Compare this checkout's ``satask`` against a baseline or an oracle.

By default the baseline is the pinned SymPy ``satask`` from the installed
``sympy`` package.  Saved baseline modules can be supplied instead::

    .venv/bin/python benchmarks/compare_satask.py \
        --baseline-satask /path/to/satask.py \
        --baseline-handlers /path/to/sathandlers.py

The saved files are loaded only in memory.  In particular, the baseline
``satask`` sees the supplied baseline handler registry even when this checkout
has already migrated its handlers to lightweight formulas.

With ``--oracle`` the pinned SymPy ``ask`` is the correctness reference
instead of the upstream ``satask`` parity check.  A definite answer that full
``ask`` cannot give (``stronger``), a missing answer (``weaker``), and a
``ValueError`` for inconsistent assumptions are all acceptable; only a
definite answer that contradicts ``ask``, or an unexpected exception, fails
the run.
"""
from __future__ import annotations

import argparse
import importlib.util
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, TypeAlias, cast

from sympy import I, Q, ask, pi, symbols
from sympy.logic.boolalg import And, Equivalent, Implies, Not, Or, Xor
from sympy.matrices.expressions import MatrixSymbol

from reasoning.satask import satask as current_satask
from reasoning.sympy_types import SymPyExpr

Outcome: TypeAlias = tuple[str, Any]

VERDICT_ORDER = ("agree", "stronger", "weaker", "inconsistent",
                 "oracle-error", "mismatch", "current-error")
FAILING_VERDICTS = ("mismatch", "current-error")


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_installed_baseline() -> Callable[..., Any]:
    """Return the pinned SymPy ``satask`` installed in this environment."""
    from sympy.assumptions.satask import satask as installed_satask
    return cast("Callable[..., Any]", installed_satask)


def load_baseline(satask_path: Path, handlers_path: Path) -> Callable[..., Any]:
    """Load a baseline SAT entry point with its matching handler module."""
    saved_handlers = sys.modules.get("reasoning.sathandlers")
    baseline_handlers = _load_module("_satask_baseline_handlers", handlers_path)
    sys.modules["reasoning.sathandlers"] = baseline_handlers
    try:
        return cast("Callable[..., Any]",
                    _load_module("_satask_baseline", satask_path).satask)
    finally:
        if saved_handlers is None:
            del sys.modules["reasoning.sathandlers"]
        else:
            sys.modules["reasoning.sathandlers"] = saved_handlers


def evaluate(function: Callable[..., Any], proposition: SymPyExpr,
             assumptions: SymPyExpr,
             early_return: bool = False) -> Outcome:
    try:
        return "value", function(proposition, assumptions, early_return=early_return)
    except Exception as error:  # Baselines can differ in their exception type.
        return "error", type(error).__name__


def evaluate_oracle(oracle: Callable[..., Any], proposition: SymPyExpr,
                    assumptions: SymPyExpr) -> Outcome:
    """Evaluate a case with SymPy's full ``ask`` as the correctness oracle."""
    try:
        return "value", oracle(proposition, assumptions)
    except Exception as error:
        return "error", type(error).__name__


def classify(current: Outcome, oracle: Outcome) -> str:
    """Classify a current/ask outcome pair.

    ``mismatch`` (two definite, different answers) and ``current-error`` (an
    unexpected exception) are the only failing verdicts.  Being stronger or
    weaker than ``ask`` is reported, not penalised, and ``ValueError`` is the
    documented outcome for inconsistent assumptions.
    """
    current_kind, current_value = current
    oracle_kind, oracle_value = oracle
    if oracle_kind == "error":
        if current_kind == "error":
            return "agree" if current_value == oracle_value else "oracle-error"
        return "oracle-error"
    if current_kind == "error":
        return "inconsistent" if current_value == "ValueError" else "current-error"
    if oracle_value is None:
        return "stronger" if current_value is not None else "agree"
    if current_value is None:
        return "weaker"
    return "agree" if current_value == oracle_value else "mismatch"


def cases(seed: int, random_cases: int) -> list[tuple[SymPyExpr, SymPyExpr]]:
    x, y, z = symbols("x y z")
    subjects = [x, y, x + y, x*y, x*y*z, x**2, x**3, x**y,
                abs(x), abs(x*y), 2, 3, I, pi]
    atoms = [predicate(subject) for subject in subjects for predicate in (
        Q.zero, Q.positive, Q.negative, Q.real, Q.integer, Q.rational,
        Q.irrational, Q.even, Q.odd, Q.imaginary,
    )]
    atoms.extend([Q.nonnegative(x), Q.nonpositive(x), Q.nonzero(x),
                  Q.prime(x*y), Q.prime(5)])
    result = [
        (Q.zero(x*y), Q.zero(x)),
        (Q.zero(x) | Q.zero(y), Q.zero(x*y)),
        (Q.real(x + y), Q.real(x) & Q.real(y)),
        (Q.integer(x*y), Q.integer(x) & Q.integer(y)),
        (Q.irrational(x*y), Q.irrational(x) & Q.rational(y) & ~Q.zero(y)),
        (Q.nonnegative(x**2), Q.positive(x)),
        (Q.zero(abs(x)), Q.zero(x)),
        (Q.even(abs(x)), Q.even(x)),
        (Q.prime(x*y), Q.prime(x) & Q.prime(y)),
        (Q.imaginary(x*y), Q.real(x) & Q.real(y)),
        (Q.zero(x**y), Q.zero(x) & Q.positive(y)),
        (Q.positive(x), Q.real(x) & ~Q.positive(x)),
    ]
    rng = random.Random(seed)

    def formula(depth: int) -> SymPyExpr:
        if depth == 0:
            return rng.choice(atoms)
        left, right = formula(depth - 1), formula(depth - 1)
        return (And(left, right), Or(left, right), Implies(left, right),
                Equivalent(left, right), Xor(left, right), Not(left))[rng.randrange(6)]

    result.extend((formula(rng.randrange(3)), formula(rng.randrange(3)))
                  for _ in range(random_cases))
    matrices = [
        (Q.diagonal(MatrixSymbol("A", 2, 2)),
         Q.lower_triangular(MatrixSymbol("A", 2, 2)) & Q.upper_triangular(MatrixSymbol("A", 2, 2))),
        (Q.invertible(MatrixSymbol("A", 2, 2)),
         Q.fullrank(MatrixSymbol("A", 2, 2)) & Q.square(MatrixSymbol("A", 2, 2))),
    ]
    return result + matrices


def compare(baseline: Callable[..., Any], seed: int, random_cases: int,
            early_return: bool = False) -> tuple[
                int, list[tuple[int, SymPyExpr, SymPyExpr,
                                tuple[str, Any], tuple[str, Any]]],
            ]:
    mismatches = []
    all_cases = cases(seed, random_cases)
    for index, (proposition, assumptions) in enumerate(all_cases):
        old = evaluate(baseline, proposition, assumptions, early_return)
        new = evaluate(current_satask, proposition, assumptions, early_return)
        if old != new:
            mismatches.append((index, proposition, assumptions, old, new))
    return len(all_cases), mismatches


def compare_with_oracle(seed: int, random_cases: int,
                        early_return: bool = False,
                        current: Callable[..., Any] = current_satask,
                        oracle: Callable[..., Any] = ask) -> tuple[
                int, Counter[str],
                list[tuple[int, SymPyExpr, SymPyExpr, Outcome, Outcome, str]],
            ]:
    """Compare current answers against the ``ask`` oracle verdict by verdict."""
    verdicts: Counter[str] = Counter()
    failures = []
    all_cases = cases(seed, random_cases)
    for index, (proposition, assumptions) in enumerate(all_cases):
        current_outcome = evaluate(current, proposition, assumptions, early_return)
        oracle_outcome = evaluate_oracle(oracle, proposition, assumptions)
        verdict = classify(current_outcome, oracle_outcome)
        verdicts[verdict] += 1
        if verdict in FAILING_VERDICTS:
            failures.append((index, proposition, assumptions,
                             current_outcome, oracle_outcome, verdict))
    return len(all_cases), verdicts, failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-satask", type=Path,
                        help="a saved baseline satask.py file")
    parser.add_argument("--baseline-handlers", type=Path,
                        help="the saved sathandlers.py matching --baseline-satask")
    parser.add_argument("--oracle", action="store_true",
                        help="benchmark against SymPy's ask as the correctness "
                             "oracle instead of upstream satask parity")
    parser.add_argument("--seed", type=int, default=62819)
    parser.add_argument("--random-cases", type=int, default=120)
    parser.add_argument("--include-early-return", action="store_true")
    args = parser.parse_args()

    if args.oracle and args.baseline_satask is not None:
        parser.error("--oracle cannot be combined with a saved baseline")
    if (args.baseline_satask is None) != (args.baseline_handlers is None):
        parser.error("--baseline-satask and --baseline-handlers are required together")
    modes = [False] + ([True] if args.include_early_return else [])
    failed = False
    if args.oracle:
        for early_return in modes:
            count, verdicts, failures = compare_with_oracle(
                args.seed, args.random_cases, early_return)
            mode = "early_return" if early_return else "full SAT"
            summary = ", ".join(f"{verdicts[verdict]} {verdict}"
                                for verdict in VERDICT_ORDER if verdicts[verdict])
            print(f"{mode}: {count} cases: {summary}")
            for index, proposition, assumptions, current, oracle, verdict in failures:
                print(f"  {verdict} case {index}: {proposition!s} "
                      f"under {assumptions!s}")
                print(f"    current={current}; ask oracle={oracle}")
            failed |= bool(failures)
    else:
        if args.baseline_satask is None:
            baseline = load_installed_baseline()
        else:
            baseline = load_baseline(args.baseline_satask, args.baseline_handlers)
        for early_return in modes:
            count, mismatches = compare(baseline, args.seed,
                                        args.random_cases, early_return)
            mode = "early_return" if early_return else "full SAT"
            print(f"{mode}: {count} cases, {len(mismatches)} mismatches")
            for index, proposition, assumptions, old, new in mismatches:
                print(f"  case {index}: {proposition!s} under {assumptions!s}")
                print(f"    baseline={old}; current={new}")
            failed |= bool(mismatches)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
