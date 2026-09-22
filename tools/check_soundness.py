"""Soundness audit for :func:`reasoning.satask.satask`.

The validation suites measure how many queries ``satask`` answers; they do not
check whether a definite answer is *true*.  This script generates queries and
checks definite answers against two independent oracles:

* Concrete models.  Every symbol is assigned a value, the assumptions are
  evaluated with SymPy's ``ask`` on the resulting ground atoms, and only
  assignments that satisfy the assumptions are kept.  A definite answer that a
  satisfying assignment contradicts is unsound.
* SymPy's full ``ask``.  When ``ask`` returns a definite answer for the same
  query and ``satask`` returns the opposite, the result is reported.

Only unsoundness is reported: ``None`` where ``ask`` is definite is expected
while handlers are still being added and is not a finding.  The audit also
reports assumptions that raise ``Inconsistent assumptions`` even though a model
exists, and queries where a proposition and its negation both get the same
definite answer.

Some handlers deliberately mirror SymPy rules that a concrete model can
contradict, such as the closed-group rule that a sum of imaginary arguments is
imaginary even when the sum cancels.  A model counterexample is therefore only
reported when SymPy's ``ask`` does not return the same definite answer.  Use
``--strict`` to report those upstream-shared counterexamples as well.

Random queries come from Hypothesis, which shrinks each finding to a minimal
example.  Generated assumptions are satisfied by the model that ships with the
example, so no query is rejected for lack of a model.  ``--engine random``
selects the seedable stdlib generator instead, which reports every finding it
encounters rather than one minimized example per run.

The audit imports ``reasoning`` from the environment; point ``PYTHONPATH`` at
another checkout to audit its handlers::

    .venv/bin/python tools/check_soundness.py
    PYTHONPATH=/path/to/checkout .venv/bin/python tools/check_soundness.py \
        --cases 200
    .venv/bin/python tools/check_soundness.py --engine random --seed 7

Exit status is 1 when any finding is reported.  A curated list of regression
cases derived from handler audits runs before the random cases.
"""
from __future__ import annotations

import argparse
import operator
import random
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn
from sympy import (
    Abs, E, I, Q, Rational, S, ask, cos, exp, im, log, pi, re, sin, sqrt,
    symbols,
)
from sympy.assumptions.assume import AppliedPredicate
from sympy.logic.boolalg import (
    And, Equivalent, Implies, Not, Or, Xor, simplify_logic,
)
from sympy.matrices.expressions import MatrixSymbol
from sympy.matrices.immutable import ImmutableMatrix

from reasoning.satask import satask

Formula = Any
SataskFn = Callable[..., Any]
AskFn = Callable[..., Any]

SCALAR_VALUES: tuple[Any, ...] = (
    S.Zero, S.One, S.NegativeOne, S(2), S(-2), S.Half, Rational(2, 3),
    Rational(-3, 2), I, -I, 2*I, 1 + I, 1 - I, sqrt(2), -sqrt(2), pi, E,
    exp(2*pi), exp(pi), log(2), 3 + 4*I,
)

MATRIX_VALUES: tuple[Any, ...] = (
    ImmutableMatrix([[1, 0], [0, 1]]),
    ImmutableMatrix([[1, 0], [0, 2]]),
    ImmutableMatrix([[1, 1], [0, 1]]),
    ImmutableMatrix([[1, 1], [1, 1]]),
    ImmutableMatrix([[0, 1], [1, 0]]),
    ImmutableMatrix([[0, 1], [-1, 0]]),
    ImmutableMatrix([[1, I], [-I, 1]]),
    ImmutableMatrix([[I, 0], [0, I]]),
    ImmutableMatrix([[1, 2], [3, 4]]),
    ImmutableMatrix([[1, 0], [0, 0]]),
)

CONSTANTS: tuple[Any, ...] = (
    S.Zero, S.One, S.NegativeOne, S(2), I, pi, Rational(1, 2), E,
)

SCALAR_PREDICATES: tuple[Any, ...] = (
    Q.zero, Q.nonzero, Q.positive, Q.negative, Q.nonnegative, Q.nonpositive,
    Q.real, Q.extended_real, Q.imaginary, Q.complex, Q.integer, Q.rational,
    Q.irrational, Q.algebraic, Q.transcendental, Q.even, Q.odd, Q.prime,
    Q.composite, Q.finite, Q.infinite, Q.hermitian, Q.antihermitian,
    Q.commutative,
)

MATRIX_PREDICATES: tuple[Any, ...] = (
    Q.square, Q.invertible, Q.fullrank, Q.symmetric, Q.diagonal,
    Q.lower_triangular, Q.upper_triangular, Q.orthogonal, Q.unitary,
    Q.positive_definite, Q.singular, Q.hermitian,
)

RELATION_PREDICATES: tuple[Any, ...] = (Q.eq, Q.ne, Q.gt, Q.ge, Q.lt, Q.le)

x, y, z = symbols("x y z")
A, B = MatrixSymbol("A", 2, 2), MatrixSymbol("B", 2, 2)

SCALAR_SYMBOLS: tuple[Any, ...] = (x, y, z)
MATRIX_SYMBOLS: tuple[Any, ...] = (A, B)

CURATED_MODEL_COUNT = 32
CURATED_MODEL_TRIES = 400

CURATED_CASES: tuple[tuple[Any, Any, str], ...] = (
    (Q.hermitian(x + I), Q.imaginary(x), "hermitian(x + I) | imaginary(x)"),
    (Q.positive(x**I), Q.positive(x), "positive(x**I) | positive(x)"),
    (Q.algebraic(exp(x)), Q.algebraic(x), "algebraic(exp(x)) | algebraic(x)"),
    (Q.hermitian(I*x), Q.hermitian(x), "hermitian(I*x) | hermitian(x)"),
    (Q.imaginary(x + y), Q.imaginary(x) & Q.imaginary(y),
     "imaginary(x + y) | imaginary(x) & imaginary(y)"),
    (Q.negative(-I + I*(cos(2)**2 + sin(2)**2)), True,
     "negative(-I + I*(cos(2)**2 + sin(2)**2))"),
    (Q.complex(1/x), Q.complex(x), "complex(1/x) | complex(x)"),
    (Q.zero(x), ~Q.complex(1/x), "zero(x) | ~complex(1/x)"),
    (Q.integer(sqrt(2)*x), Q.integer(x), "integer(sqrt(2)*x) | integer(x)"),
    (Q.real(x*y), Q.real(x) & Q.real(y), "real(x*y) | real(x) & real(y)"),
    (Q.zero(x*y), Q.zero(x), "zero(x*y) | zero(x)"),
    (Q.positive(x + y), Q.positive(x) & Q.positive(y),
     "positive(x + y) | positive(x) & positive(y)"),
)


@dataclass(frozen=True)
class Case:
    proposition: Any
    premises: Any
    label: str
    model_count: int = 12
    model_tries: int = 200
    model: dict[Any, Any] | None = None


@dataclass(frozen=True)
class Finding:
    kind: str
    case: Case
    detail: str

    def format(self) -> str:
        return (f"{self.kind}: {self.case.label}\n"
                f"  proposition: {self.case.proposition}\n"
                f"  assumptions: {self.case.premises}\n"
                f"  {self.detail}")


@dataclass(frozen=True)
class CaseReport:
    findings: tuple[Finding, ...]
    has_model: bool
    suppressed: int = 0


def ground_truth(formula: Any, values: dict[Any, Any]) -> bool | None:
    """Evaluate a ground formula with ``ask``, or None if an atom is unknown."""
    if formula is True:
        return True
    if formula is False:
        return False
    try:
        substituted = formula.subs(values)
        replacements: dict[Any, Any] = {}
        for atom in substituted.atoms(AppliedPredicate):
            truth = ask(atom)
            if truth is None:
                return None
            replacements[atom] = S.true if truth is True else S.false
        ground = substituted.xreplace(replacements)
        if ground is S.true:
            return True
        if ground is S.false:
            return False
        simplified = simplify_logic(ground)
    except Exception:
        return None
    if simplified is S.true:
        return True
    if simplified is S.false:
        return False
    return None


def find_models(case: Case, scalar_symbols: Sequence[Any],
                matrix_symbols: Sequence[Any], rng: random.Random,
                count: int, tries: int) -> list[dict[Any, Any]]:
    """Return up to ``count`` distinct assignments satisfying the assumptions."""
    models: list[dict[Any, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for _ in range(tries):
        if len(models) >= count:
            break
        values: dict[Any, Any] = {
            symbol: rng.choice(SCALAR_VALUES) for symbol in scalar_symbols}
        values.update(
            {symbol: rng.choice(MATRIX_VALUES) for symbol in matrix_symbols})
        if ground_truth(case.premises, values) is not True:
            continue
        key = tuple(sorted((str(symbol), repr(value))
                           for symbol, value in values.items()))
        if key not in seen:
            seen.add(key)
            models.append(values)
    return models


def _call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[str, Any]:
    try:
        return "value", function(*args, **kwargs)
    except Exception as error:
        return "error", error


def _inconsistent(error: BaseException) -> bool:
    return "inconsistent" in str(error).lower()


def _counterexample_note(proposition: Any, models: Sequence[dict[Any, Any]],
                         wanted: bool) -> str | None:
    for model in models:
        if ground_truth(proposition, model) is wanted:
            return f"model {model} makes the proposition {wanted}"
    return None


def _oracle_answer(ask_fn: AskFn, case: Case) -> Any:
    status, oracle = _call(ask_fn, case.proposition, case.premises)
    return oracle if status == "value" else None


def _counterexample(findings: list[Finding], case: Case,
                    models: Sequence[dict[Any, Any]], result: Any,
                    oracle: Any, strict: bool) -> int:
    if result is not True and result is not False:
        return 0
    note = _counterexample_note(case.proposition, models, not result)
    if note is None:
        return 0
    if strict or oracle != result:
        findings.append(Finding("counterexample", case, note))
        return 0
    return 1


def audit_case(case: Case, scalar_symbols: Sequence[Any],
               matrix_symbols: Sequence[Any],
               rng: random.Random | None,
               satask_fn: SataskFn, ask_fn: AskFn, *,
               early_return: bool = False,
               use_oracle: bool = True,
               strict: bool = False) -> CaseReport:
    if case.model is not None:
        models = [case.model]
    elif rng is not None:
        models = find_models(case, scalar_symbols, matrix_symbols, rng,
                             case.model_count, case.model_tries)
    else:
        models = []
    if not models:
        return CaseReport((), False)

    findings: list[Finding] = []
    status, result = _call(satask_fn, case.proposition, case.premises)
    if status == "error":
        kind = "spurious-inconsistency" if _inconsistent(result) else "exception"
        findings.append(Finding(
            kind, case,
            f"raised {type(result).__name__}: {result}; "
            f"{len(models)} model(s) satisfy the assumptions, e.g. {models[0]}"))
        return CaseReport(tuple(findings), True)

    oracle = _oracle_answer(ask_fn, case) if use_oracle else None
    if oracle is not None and result is not None and oracle != result:
        findings.append(Finding(
            "oracle-disagreement", case,
            f"satask={result} but sympy.ask={oracle}"))

    status, negated = _call(
        satask_fn, Not(case.proposition), case.premises)
    if status == "value" and result is not None and result == negated:
        findings.append(Finding(
            "both-polars", case,
            f"proposition and negation both {result}; model {models[0]}"))

    suppressed = _counterexample(findings, case, models, result, oracle, strict)

    if early_return:
        status, early = _call(
            satask_fn, case.proposition, case.premises,
            early_return=True)
        if status == "value" and early is not None:
            if result is not None and early != result:
                findings.append(Finding(
                    "early-return-disagreement", case,
                    f"early_return={early} but full={result}"))
            suppressed += _counterexample(
                findings, case, models, early, oracle, strict)

    return CaseReport(tuple(findings), True, suppressed)


def random_scalar(rng: random.Random, scalar_symbols: Sequence[Any],
                  depth: int) -> Any:
    if depth <= 0 or rng.random() < 0.35:
        return rng.choice((*scalar_symbols, *CONSTANTS))
    left = random_scalar(rng, scalar_symbols, depth - 1)
    right = random_scalar(rng, scalar_symbols, depth - 1)
    operation = rng.randrange(11)
    if operation == 0:
        return left + right
    if operation == 1:
        return left*right
    if operation == 2:
        return left**rng.choice((2, 3, -1, I))
    if operation == 3:
        return -left
    if operation == 4:
        return Abs(left)
    if operation == 5:
        return sin(left)
    if operation == 6:
        return cos(left)
    if operation == 7:
        return exp(left)
    if operation == 8:
        return log(left)
    if operation == 9:
        return re(left)
    return im(left)


def random_atom(rng: random.Random, scalar_symbols: Sequence[Any],
                matrix_symbols: Sequence[Any]) -> Any:
    if matrix_symbols and rng.random() < 0.2:
        return rng.choice(MATRIX_PREDICATES)(rng.choice(matrix_symbols))
    return rng.choice(SCALAR_PREDICATES)(
        random_scalar(rng, scalar_symbols, 2))


def random_literal(rng: random.Random, scalar_symbols: Sequence[Any],
                   matrix_symbols: Sequence[Any]) -> Any:
    atom = random_atom(rng, scalar_symbols, matrix_symbols)
    return Not(atom) if rng.random() < 0.4 else atom


def random_formula(rng: random.Random, scalar_symbols: Sequence[Any],
                   matrix_symbols: Sequence[Any], depth: int) -> Any:
    if depth <= 0:
        return random_literal(rng, scalar_symbols, matrix_symbols)
    left = random_formula(rng, scalar_symbols, matrix_symbols, depth - 1)
    right = random_formula(rng, scalar_symbols, matrix_symbols, depth - 1)
    return (And(left, right), Or(left, right), Implies(left, right),
            Equivalent(left, right), Xor(left, right))[rng.randrange(5)]


def random_assumptions(rng: random.Random, scalar_symbols: Sequence[Any],
                       matrix_symbols: Sequence[Any],
                       relations: bool) -> Any:
    literals = [random_literal(rng, scalar_symbols, matrix_symbols)
                for _ in range(rng.randint(1, 3))]
    if relations and scalar_symbols and rng.random() < 0.3:
        operands = (*scalar_symbols, S.Zero, S.One, S(2), pi, E)
        left = rng.choice(operands)
        right = rng.choice(operands)
        literals.append(rng.choice(RELATION_PREDICATES)(left, right))
    return And(*literals)


def random_cases(rng: random.Random, count: int,
                 scalar_symbols: Sequence[Any],
                 matrix_symbols: Sequence[Any],
                 relations: bool, model_count: int,
                 model_tries: int) -> list[Case]:
    cases = []
    for index in range(count):
        case_rng = random.Random(f"{rng.random()}-{index}")
        proposition = random_formula(case_rng, scalar_symbols,
                                     matrix_symbols, case_rng.randint(1, 2))
        assumptions = random_assumptions(case_rng, scalar_symbols,
                                         matrix_symbols, relations)
        cases.append(Case(proposition, assumptions, f"random-{index}",
                          model_count, model_tries))
    return cases


def scalar_strategy() -> Any:
    return st.recursive(
        st.sampled_from((*SCALAR_SYMBOLS, *CONSTANTS)),
        lambda children: st.one_of(
            st.builds(operator.add, children, children),
            st.builds(operator.mul, children, children),
            st.builds(operator.pow, children, st.sampled_from((2, 3, -1, I))),
            st.builds(operator.neg, children),
            st.builds(Abs, children),
            st.builds(sin, children),
            st.builds(cos, children),
            st.builds(exp, children),
            st.builds(log, children),
            st.builds(re, children),
            st.builds(im, children),
        ),
        max_leaves=6,
    )


def atom_strategy(matrices: bool) -> Any:
    scalar = st.builds(
        lambda predicate, subject: predicate(subject),
        st.sampled_from(SCALAR_PREDICATES), scalar_strategy())
    if not matrices:
        return scalar
    matrix = st.builds(
        lambda predicate, subject: predicate(subject),
        st.sampled_from(MATRIX_PREDICATES), st.sampled_from(MATRIX_SYMBOLS))
    return st.one_of(scalar, matrix)


def formula_strategy(matrices: bool) -> Any:
    atoms = atom_strategy(matrices)
    return st.recursive(
        atoms,
        lambda children: st.one_of(
            st.builds(And, children, children),
            st.builds(Or, children, children),
            st.builds(Implies, children, children),
            st.builds(Equivalent, children, children),
            st.builds(Xor, children, children),
            st.builds(Not, children),
        ),
        max_leaves=4,
    )


@st.composite
def hypothesis_cases(draw: DrawFn, matrices: bool = True) -> Case:
    """Generate a query together with a model satisfying its assumptions."""
    values: dict[Any, Any] = {
        symbol: draw(st.sampled_from(SCALAR_VALUES))
        for symbol in SCALAR_SYMBOLS}
    if matrices:
        values.update({
            symbol: draw(st.sampled_from(MATRIX_VALUES))
            for symbol in MATRIX_SYMBOLS})
    atoms = draw(st.lists(atom_strategy(matrices), min_size=1, max_size=3))
    literals = []
    for atom in atoms:
        truth = ground_truth(atom, values)
        if truth is True:
            literals.append(atom)
        elif truth is False:
            literals.append(Not(atom))
    proposition = draw(formula_strategy(matrices))
    return Case(proposition, And(*literals), "hypothesis", model=values)


class UnsoundnessFound(Exception):
    def __init__(self, findings: Sequence[Finding]) -> None:
        super().__init__(f"{len(findings)} finding(s)")
        self.findings = tuple(findings)


def run_hypothesis(satask_fn: SataskFn = satask, ask_fn: AskFn = ask, *,
                   matrices: bool = True, max_examples: int = 60,
                   early_return: bool = False, use_oracle: bool = True,
                   strict: bool = False,
                   derandomize: bool = False) -> tuple[list[Finding], int]:
    suppressed = [0]

    @settings(max_examples=max_examples, deadline=None, database=None,
              derandomize=derandomize,
              suppress_health_check=[HealthCheck.too_slow,
                                     HealthCheck.filter_too_much])
    @given(hypothesis_cases(matrices))
    def check(case: Case) -> None:
        report = audit_case(
            case, SCALAR_SYMBOLS, MATRIX_SYMBOLS, None, satask_fn, ask_fn,
            early_return=early_return, use_oracle=use_oracle, strict=strict)
        suppressed[0] += report.suppressed
        if report.findings:
            raise UnsoundnessFound(report.findings)

    try:
        check()
    except UnsoundnessFound as error:
        return list(error.findings), suppressed[0]
    return [], suppressed[0]


def run_audit(cases: Sequence[Case], scalar_symbols: Sequence[Any],
              matrix_symbols: Sequence[Any], *,
              satask_fn: SataskFn = satask, ask_fn: AskFn = ask,
              seed: int = 30222, early_return: bool = False,
              use_oracle: bool = True, strict: bool = False,
              verbose: bool = False) -> tuple[list[Finding], int, int, int]:
    findings: list[Finding] = []
    accepted = 0
    skipped = 0
    suppressed = 0
    for index, case in enumerate(cases):
        rng = random.Random(f"{seed}-{index}")
        report = audit_case(
            case, scalar_symbols, matrix_symbols, rng, satask_fn, ask_fn,
            early_return=early_return, use_oracle=use_oracle, strict=strict)
        findings.extend(report.findings)
        accepted += report.has_model
        skipped += not report.has_model
        suppressed += report.suppressed
        if verbose:
            state = "model" if report.has_model else "skip"
            print(f"  [{state}] {case.label}: {len(report.findings)} finding(s)")
    return findings, accepted, skipped, suppressed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("hypothesis", "random"),
                        default="hypothesis",
                        help="random query generator to use")
    parser.add_argument("--seed", type=int, default=30222,
                        help="seed for the random engine")
    parser.add_argument("--cases", type=int, default=60,
                        help="random queries to generate (max examples for "
                             "the hypothesis engine)")
    parser.add_argument("--model-count", type=int, default=12,
                        help="models to collect per query")
    parser.add_argument("--model-tries", type=int, default=200,
                        help="assignment samples per query")
    parser.add_argument("--derandomize", action="store_true",
                        help="use a fixed Hypothesis seed for reproducibility")
    parser.add_argument("--no-oracle", action="store_true",
                        help="skip the sympy.ask oracle comparison")
    parser.add_argument("--no-matrices", action="store_true",
                        help="do not generate matrix predicates")
    parser.add_argument("--no-relations", action="store_true",
                        help="do not generate relation assumptions")
    parser.add_argument("--early-return", action="store_true",
                        help="also audit early_return=True answers")
    parser.add_argument("--strict", action="store_true",
                        help="report counterexamples that sympy.ask also gives")
    parser.add_argument("--verbose", action="store_true",
                        help="print each case as it is audited")
    arguments = parser.parse_args(argv)

    scalar_symbols = SCALAR_SYMBOLS
    matrix_symbols = () if arguments.no_matrices else MATRIX_SYMBOLS
    curated = [Case(proposition, assumptions, label, CURATED_MODEL_COUNT,
                    max(CURATED_MODEL_TRIES, arguments.model_tries))
               for proposition, assumptions, label in CURATED_CASES]
    findings, accepted, skipped, suppressed = run_audit(
        curated, scalar_symbols, matrix_symbols, seed=arguments.seed,
        early_return=arguments.early_return,
        use_oracle=not arguments.no_oracle, strict=arguments.strict)
    summary = [f"{accepted} curated queries with a model",
               f"{skipped} skipped"]
    if arguments.engine == "hypothesis":
        if arguments.cases:
            generated_findings, generated_suppressed = run_hypothesis(
                matrices=not arguments.no_matrices,
                max_examples=arguments.cases,
                early_return=arguments.early_return,
                use_oracle=not arguments.no_oracle, strict=arguments.strict,
                derandomize=arguments.derandomize)
            findings.extend(generated_findings)
            suppressed += generated_suppressed
            summary.append(f"{arguments.cases} hypothesis examples")
        else:
            summary.append("hypothesis generation disabled")
    else:
        generator = random.Random(arguments.seed)
        generated = random_cases(
            generator, arguments.cases, scalar_symbols, matrix_symbols,
            not arguments.no_relations, arguments.model_count,
            arguments.model_tries)
        generated_findings, accepted, skipped, generated_suppressed = run_audit(
            generated, scalar_symbols, matrix_symbols, seed=arguments.seed,
            early_return=arguments.early_return,
            use_oracle=not arguments.no_oracle, strict=arguments.strict,
            verbose=arguments.verbose)
        findings.extend(generated_findings)
        suppressed += generated_suppressed
        summary.append(f"{accepted} random queries with a model")
        summary.append(f"{skipped} skipped")
    for finding in findings:
        print(finding.format())
    print(f"\n{', '.join(summary)}, {len(findings)} finding(s), "
          f"{suppressed} upstream-shared counterexample(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
