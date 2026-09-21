"""Compare the bundled DPLL solver with the Rust core on the satask pipeline.

Run with::

    .venv/bin/python -m benchmarks.rust_compare --repeat 25
    .venv/bin/python -m benchmarks.rust_compare --repeat 50 --solver-only

Cases and phases mirror ``benchmarks.satask`` so the numbers are comparable.
Both solvers run alternately in one process, and per-case medians are reported.
The Rust library is located by :mod:`reasoning.rust_solver`.
"""
import argparse
import statistics
from time import perf_counter
from typing import Any, Callable

from reasoning.clauses import assert_formula, compile_formula
from reasoning.engine import ReasoningEngine
from reasoning.rust_solver import RustSolver, rust_signature
from reasoning.satask import get_all_relevant_facts
from reasoning.solver import SATSolver
from reasoning.sympy_adapter import to_formula
from reasoning.sympy_types import SymPyExpr

from benchmarks.satask import cases

SolverClass = Callable[..., Any]


def measure(proposition: SymPyExpr, assumptions: SymPyExpr,
            solver_class: SolverClass) -> dict[str, Any]:
    start = perf_counter()
    prop, assump = to_formula(proposition), to_formula(assumptions)
    converted = perf_counter()
    db = get_all_relevant_facts(prop, assump)
    discovered = perf_counter()
    assert_formula(assump, db)
    query = compile_formula(prop, db)
    encoded = perf_counter()
    result: bool | str | None
    try:
        result = ReasoningEngine(db, solver_class).ask(query)
    except ValueError:
        result = 'inconsistent'
    solved = perf_counter()
    return {
        'conversion_ms': (converted-start)*1000,
        'discovery_encoding_ms': (discovered-converted)*1000,
        'query_encoding_ms': (encoded-discovered)*1000,
        'solve_ms': (solved-encoded)*1000,
        'total_ms': (solved-start)*1000,
        'clauses': len(db.data), 'variables': len(db.variables), 'result': result,
    }


def engine_only(proposition: SymPyExpr, assumptions: SymPyExpr,
                solver_class: SolverClass) -> tuple[float, bool | str | None, int, int]:
    """Time only ``ReasoningEngine`` over a database built once before timing."""
    prop, assump = to_formula(proposition), to_formula(assumptions)
    db = get_all_relevant_facts(prop, assump)
    assert_formula(assump, db)
    query = compile_formula(prop, db)
    start = perf_counter()
    try:
        result: bool | str | None = ReasoningEngine(db, solver_class).ask(query)
    except ValueError:
        result = 'inconsistent'
    elapsed = (perf_counter() - start) * 1000
    return elapsed, result, len(db.data), len(db.variables)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeat', type=int, default=25)
    parser.add_argument('--solver-only', action='store_true',
                        help='time ReasoningEngine alone on prebuilt databases')
    args = parser.parse_args()

    solvers: dict[str, SolverClass] = {
        'dpll': SATSolver,
        'rust': RustSolver,
    }
    print(f"rust core: {rust_signature()}")

    for name, inputs in cases().items():
        for solver_class in solvers.values():
            measure(*inputs, solver_class)
        results: dict[str, list[dict[str, Any]]] = {key: [] for key in solvers}
        for _ in range(args.repeat):
            for key, solver_class in solvers.items():
                results[key].append(measure(*inputs, solver_class))
        print(f"\n[{name}] clauses={results['dpll'][-1]['clauses']} "
              f"variables={results['dpll'][-1]['variables']}")
        print(f"  {'solver':8} {'result':>12} {'conversion':>11} {'discovery':>10} "
              f"{'query_enc':>10} {'solve':>10} {'total':>10}")
        for key, runs in results.items():
            median = {field: statistics.median(run[field] for run in runs)
                      for field in runs[-1] if field.endswith('_ms')}
            print(f"  {key:8} {str(runs[-1]['result']):>12} "
                  f"{median['conversion_ms']:11.4f} {median['discovery_encoding_ms']:10.3f} "
                  f"{median['query_encoding_ms']:10.4f} {median['solve_ms']:10.3f} "
                  f"{median['total_ms']:10.3f}")
        dpll = statistics.median(run['total_ms'] for run in results['dpll'])
        rust = statistics.median(run['total_ms'] for run in results['rust'])
        print(f"  total speedup: {dpll/rust:.2f}x "
              f"(solve-only {statistics.median(run['solve_ms'] for run in results['dpll'])/statistics.median(run['solve_ms'] for run in results['rust']):.2f}x)")

    if args.solver_only:
        print('\nengine-only (ReasoningEngine construction/ask on prebuilt db)')
        for name, inputs in cases().items():
            for solver_class in solvers.values():
                engine_only(*inputs, solver_class)
            timings: dict[str, list[float]] = {key: [] for key in solvers}
            outcomes: dict[str, Any] = {}
            for _ in range(args.repeat):
                for key, solver_class in solvers.items():
                    elapsed, result, _, _ = engine_only(*inputs, solver_class)
                    timings[key].append(elapsed)
                    outcomes[key] = result
            dpll = statistics.median(timings['dpll'])
            rust = statistics.median(timings['rust'])
            print(f"  {name:14} dpll={dpll:8.3f}ms rust={rust:8.3f}ms "
                  f"{dpll/rust:6.2f}x  results={outcomes}")


if __name__ == '__main__':
    main()
