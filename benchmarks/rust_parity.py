"""Check that the Rust core and the bundled solver give identical satask answers.

Run with::

    .venv/bin/python -m benchmarks.rust_parity --random-cases 300

Reuses the random case generator from ``benchmarks.compare_satask`` and runs
each case through both backends in one process by swapping the engine class
``satask`` uses.
"""
import argparse
from typing import Any, Callable, cast

import reasoning.satask as satask_module
from reasoning.rust_solver import RustSolver
from reasoning.solver import SATSolver

from benchmarks.compare_satask import cases


def run_all(solver_class: type, seed: int, random_cases: int,
            early_return: bool) -> list[tuple[str, object]]:
    module = cast(Any, satask_module)
    original: Callable[..., Any] = module.ReasoningEngine
    module.ReasoningEngine = lambda db, _cls=solver_class: original(db, _cls)
    results: list[tuple[str, object]] = []
    try:
        for proposition, assumptions in cases(seed, random_cases):
            value: object
            try:
                value = satask_module.satask(proposition, assumptions,
                                             early_return=early_return)
            except Exception as error:
                value = f"{type(error).__name__}: {error}"
            results.append((str(proposition), value))
    finally:
        module.ReasoningEngine = original
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=62819)
    parser.add_argument("--random-cases", type=int, default=300)
    args = parser.parse_args()

    failed = False
    for early_return in (False, True):
        bundled = run_all(SATSolver, args.seed, args.random_cases, early_return)
        rust = run_all(RustSolver, args.seed, args.random_cases, early_return)
        mismatches = [(index, left, right) for index, (left, right)
                      in enumerate(zip(bundled, rust)) if left != right]
        mode = "early_return" if early_return else "full SAT"
        print(f"{mode}: {len(bundled)} cases, {len(mismatches)} mismatches")
        for index, left, right in mismatches[:10]:
            print(f"  case {index}: {left}")
            print(f"    dpll={left[1]}; rust={right[1]}")
        failed |= bool(mismatches)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
