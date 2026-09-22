"""Compare satask backends by running the validation suites against each.

Example::

    .venv/bin/python validation/compare_backends.py

``validation/test_query.py`` and ``validation/test_matrices.py`` re-export
SymPy's pinned upstream suites with ``ask`` and ``_ask_recursive`` rebound to
this checkout's ``satask``; ``validation/test_refine.py`` re-exports SymPy's
refine suite with ``refine`` and ``refine_sin_cos`` rebound to
``reasoning.refine`` and is run with ``--suite validation/test_refine.py``.
The SymPy backend runs temporary re-exports of the same upstream suites with
those names rebound to SymPy's own implementations.  Each backend runs in its
own pytest subprocess; per-test outcomes, timings, and failure texts are
compared.  An outcome where reasoning passes and SymPy does not is an
improvement, and tests both backends fail with different failure content are
expected to diverge as reasoning gets further: both are reported for
inspection but do not affect the exit status.  The exit status is 1 only when
the backends otherwise disagree on an outcome (for example, SymPy passes a
test reasoning fails); it is 0 otherwise.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITES = (Path(__file__).resolve().parent / "test_query.py",
                  Path(__file__).resolve().parent / "test_matrices.py")
BACKENDS = ("reasoning", "sympy")
SYMPY_PACKAGE = "sympy.assumptions.tests"
SYMPY_BACKEND_SUITE = f"""\
from {SYMPY_PACKAGE} import {{module}} as _suite
from sympy.assumptions.satask import satask as _satask

_suite.ask = _satask
_suite._ask_recursive = _satask

from {SYMPY_PACKAGE}.{{module}} import *  # noqa: E402,F401,F403
"""
REASONING_BINDINGS = ("from reasoning.satask import satask",
                      "from reasoning.refine import refine")

OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(\S+)", re.MULTILINE)
OUTCOMES = ("PASSED", "FAILED", "ERROR", "XFAIL", "XPASS", "SKIPPED")
PASSING_OUTCOMES = ("PASSED", "XPASS")
BACKEND_SUFFIX = re.compile(r"_(?:reasoning|sympy)\b")


def passes(outcome: str | None) -> bool:
    return outcome in PASSING_OUTCOMES


def write_sympy_suite(directory: Path, suite: Path) -> Path:
    target = directory / f"{suite.stem}_sympy.py"
    target.write_text(SYMPY_BACKEND_SUITE.format(module=suite.stem))
    return target


def comparison_key(nodeid: str) -> str:
    parts = nodeid.split("::")
    stem = BACKEND_SUFFIX.sub("", Path(parts[0]).stem)
    return "::".join([stem, *parts[1:]])


def normalize_failure(text: str, roots: tuple[Path, ...]) -> str:
    for root in roots:
        text = text.replace(str(root), "<repo>")
    text = re.sub(r"/(?:[A-Za-z.~][\w@.-]*/)+[A-Za-z.~][\w@.-]*", "<abs>", text)
    text = re.sub(r"(<(?:abs|repo)>):\d+", r"\1", text)
    text = BACKEND_SUFFIX.sub("", text)
    text = re.sub(r"\.py:\d+", ".py", text)
    text = re.sub(r"0x[0-9a-fA-F]+", "0x...", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\s*(?:s\b|seconds\b)", "<time>", text)
    return " ".join(text.split())


def run_pytest(suites: list[Path], report: Path, pytest_args: list[str]) -> tuple[str, float]:
    command = [
        sys.executable, "-m", "pytest", *[str(suite) for suite in suites],
        "-q", "--tb=no", "-rA", "--color=no", "--no-header",
        "-p", "no:cacheprovider", f"--junit-xml={report}", *pytest_args,
    ]
    start = perf_counter()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return result.stdout + result.stderr, perf_counter() - start


def parse_outcomes(output: str) -> dict[str, str]:
    outcomes = {}
    for outcome, nodeid in OUTCOME.findall(output):
        outcomes[comparison_key(nodeid)] = outcome
    return outcomes


def parse_report(report: Path, tmpdir: Path) -> tuple[dict[str, float], dict[str, str]]:
    """Return per-test timings and normalized failure texts from the JUnit XML."""
    if not report.exists():
        return {}, {}
    timings, failures = {}, {}
    for case in ET.parse(report).getroot().iter("testcase"):
        module = case.get("classname", "").rsplit(".", 1)[-1]
        key = f"{BACKEND_SUFFIX.sub('', module)}::{case.get('name')}"
        time = case.get("time")
        timings[key] = float(time) if time is not None else 0.0
        for node in case:
            if node.tag in ("failure", "error"):
                text = f"{node.get('message', '')}\n{node.text or ''}"
                failures[key] = normalize_failure(text, (ROOT, tmpdir))
    return timings, failures


def run_backend(backend: str, suites: list[Path],
                pytest_args: list[str]) -> tuple[dict[str, str], dict[str, float],
                                                 dict[str, str], float]:
    with tempfile.TemporaryDirectory(dir=suites[0].parent) as directory_name:
        directory = Path(directory_name)
        targets = suites if backend == "reasoning" else [
            write_sympy_suite(directory, suite) for suite in suites]
        output, wall = run_pytest(targets, directory / "report.xml", pytest_args)
        timings, failures = parse_report(directory / "report.xml", directory)
    outcomes = parse_outcomes(output)
    if not outcomes:
        print(output, file=sys.stderr)
        raise SystemExit(f"pytest collected no tests for the {backend} backend")
    return outcomes, timings, failures, wall


def summarize(outcomes: dict[str, str]) -> str:
    counts = Counter(outcomes.values())
    return ", ".join(f"{counts[outcome]} {outcome.lower()}" for outcome in OUTCOMES
                     if counts[outcome])


def format_time(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds:.2f}s"


def print_timings(backends: dict[str, tuple[dict[str, str], dict[str, float],
                                             dict[str, str], float]],
                  count: int) -> None:
    reasoning = backends["reasoning"][1]
    sympy_ = backends["sympy"][1]
    rows = []
    for test in reasoning.keys() | sympy_.keys():
        times = [time for time in (reasoning.get(test), sympy_.get(test))
                 if time is not None]
        rows.append((max(times), test, reasoning.get(test), sympy_.get(test)))
    rows.sort(reverse=True)
    print(f"\nslowest {min(count, len(rows))} tests:")
    print(f"  {'test':<50} {'reasoning':>10} {'sympy':>10} {'delta':>9}")
    for _, test, reasoning_time, sympy_time in rows[:count]:
        delta = ("" if reasoning_time is None or sympy_time is None
                 else f"{sympy_time - reasoning_time:+.2f}s")
        print(f"  {test:<50} {format_time(reasoning_time):>10} "
              f"{format_time(sympy_time):>10} {delta:>9}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=None, metavar="SUITE",
                        help="run this single suite instead of the default two")
    parser.add_argument("--pytest-args", nargs=argparse.REMAINDER, default=[],
                        help="extra arguments forwarded to pytest")
    parser.add_argument("--timings", type=int, default=10,
                        help="number of slowest tests to show; 0 disables")
    parser.add_argument("--verbose", action="store_true",
                        help="list each backend's failing tests")
    args = parser.parse_args()

    suites = [args.suite] if args.suite else list(DEFAULT_SUITES)
    for suite in suites:
        text = suite.read_text()
        if not any(binding in text for binding in REASONING_BINDINGS):
            raise SystemExit(f"{suite} does not bind reasoning code")

    backends = {name: run_backend(name, suites, args.pytest_args)
                for name in BACKENDS}

    for name, (outcomes, timings, _, wall) in backends.items():
        print(f"{name}: {len(outcomes)} tests: {summarize(outcomes)} "
              f"(wall {wall:.2f}s, tests {sum(timings.values()):.2f}s)")
        if args.verbose:
            for test, outcome in sorted(outcomes.items()):
                if outcome in ("FAILED", "ERROR"):
                    print(f"  {outcome} {test}")

    if args.timings:
        print_timings(backends, args.timings)

    reasoning, sympy_ = backends["reasoning"][0], backends["sympy"][0]
    differing_outcomes = [(test, reasoning.get(test), sympy_.get(test))
                          for test in sorted(reasoning.keys() | sympy_.keys())
                          if reasoning.get(test) != sympy_.get(test)]
    improvements = [mismatch for mismatch in differing_outcomes
                    if passes(mismatch[1]) and not passes(mismatch[2])]
    mismatches = [mismatch for mismatch in differing_outcomes
                  if not passes(mismatch[1]) or passes(mismatch[2])]
    if improvements:
        print(f"\n{len(improvements)} improvements "
              "(reasoning passes, sympy does not):")
        for test, reasoning_outcome, sympy_outcome in improvements:
            print(f"  {test}: reasoning={reasoning_outcome} sympy={sympy_outcome}")
    if mismatches:
        print(f"\n{len(mismatches)} outcome mismatches:")
        for test, reasoning_outcome, sympy_outcome in mismatches:
            print(f"  {test}: reasoning={reasoning_outcome} sympy={sympy_outcome}")
    elif not improvements:
        print("\nNo outcome mismatches.")

    differing = []
    for test in sorted(reasoning.keys() & sympy_.keys()):
        outcome = reasoning[test]
        if (outcome == sympy_[test] and outcome in ("FAILED", "ERROR")
                and backends["reasoning"][2].get(test) != backends["sympy"][2].get(test)):
            differing.append(test)
    if differing:
        print(f"\n{len(differing)} same outcome, different failure "
              "(informational):")
        for test in differing:
            print(f"  {test}")

    raise SystemExit(1 if mismatches else 0)


if __name__ == "__main__":
    main()
