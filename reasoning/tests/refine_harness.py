"""Fixtures and oracles for refine-handler tests.

Three kinds of oracle are provided:

* :func:`reference_ask` / :func:`use_ask`: run the local dispatcher with
  ``ask`` bound to a different implementation.  ``reference_ask`` binds
  SymPy's own :func:`~sympy.assumptions.ask.ask`, which makes the local
  result directly comparable with :func:`sympy.assumptions.refine.refine`.
* :func:`stub_ask`, :func:`scripted_ask` and :func:`recording_ask`: scripted
  ``True``/``False``/``None`` answers for ``None``-safety and blocker tests.
* :func:`assert_refinement_valid`: a numeric oracle that samples values
  satisfying the assumptions and requires the refined expression to agree
  with the original; it does not consult ``ask`` at all.

Handlers must call ``ask`` as an attribute of
``reasoning.refine._upstream`` (never import it by value) for the ask
patches here to reach them.
"""
from __future__ import annotations

from contextlib import contextmanager
from itertools import product
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence
from unittest import mock

from sympy.assumptions.ask import ask as sympy_ask
from sympy.assumptions.refine import refine as sympy_refine
from sympy.core import S
from sympy.core.numbers import I, Rational, nan, oo, pi, zoo
from sympy.core.sympify import sympify
from sympy.functions.elementary.miscellaneous import sqrt
from sympy.simplify.simplify import simplify


Ask = Callable[..., bool | None]
AskLog = list[tuple[Any, Any, bool | None]]


@contextmanager
def use_ask(fake_ask: Ask) -> Iterator[None]:
    """Patch the module-global ``ask`` that every handler calls."""
    import reasoning.refine._upstream as upstream

    with mock.patch.object(upstream, "ask", fake_ask):
        yield


@contextmanager
def reference_ask() -> Iterator[None]:
    """Bind the local ``ask`` to SymPy's ``ask``.

    Under this context a handler that is implemented correctly refines
    exactly like SymPy's own handler does.
    """
    with use_ask(sympy_ask):
        yield


def assert_refines_like_sympy(expr: Any, assumptions: Any = True) -> None:
    """Require the local dispatcher to agree with SymPy's under reference ask."""
    from reasoning.refine import refine as local_refine

    with reference_ask():
        refined = local_refine(expr, assumptions)
    expected = sympy_refine(expr, assumptions)
    assert refined == expected, (
        f"refine({expr}, {assumptions}) == {refined}, "
        f"but sympy.refine gives {expected}"
    )


def stub_ask(answers: Mapping[Any, bool | None]) -> Ask:
    """Build an ``ask`` returning scripted answers.

    ``answers`` may be keyed by the proposition itself or by
    ``str(proposition)``; anything missing answers ``None``.
    """

    def fake_ask(proposition: Any, assumptions: Any = True) -> bool | None:
        if proposition in answers:
            return answers[proposition]
        return answers.get(str(proposition))

    return fake_ask


def recording_ask(
    answers: Mapping[Any, bool | None] | None = None,
) -> tuple[Ask, AskLog]:
    """Wrap SymPy's ask (or :func:`stub_ask`) and record every query."""
    base: Ask = sympy_ask if answers is None else stub_ask(answers)
    log: AskLog = []

    def fake_ask(proposition: Any, assumptions: Any = True) -> bool | None:
        result = base(proposition, assumptions)
        log.append((proposition, assumptions, result))
        return result

    return fake_ask, log


def scripted_ask(results: Iterable[bool | None]) -> tuple[Ask, AskLog]:
    """Answer with ``results`` in order, then ``None``; record every query."""
    queue = list(results)
    log: AskLog = []

    def fake_ask(proposition: Any, assumptions: Any = True) -> bool | None:
        result = queue.pop(0) if queue else None
        log.append((proposition, assumptions, result))
        return result

    return fake_ask, log


_DEFAULT_SAMPLES: tuple[Any, ...] = (
    S.Zero, S.One, S.NegativeOne, S(2), S(-2), S(3), S(-3), S.Half,
    Rational(-1, 2), Rational(4, 3), sqrt(2), pi, S.Exp1,
    I, -I, 2 * I, -2 * I, 1 + I, 1 - I,
)


def _even(value: Any) -> bool | None:
    if value.is_integer is True:
        return int(value) % 2 == 0
    if value.is_integer is False:
        return False
    return None


def _odd(value: Any) -> bool | None:
    even = _even(value)
    return None if even is None else not even


_PREDICATE_CHECKS: dict[str, Callable[[Any], bool | None]] = {
    "positive": lambda v: v.is_positive,
    "negative": lambda v: v.is_negative,
    "zero": lambda v: v.is_zero,
    "nonzero": lambda v: None if v.is_zero is None else not v.is_zero,
    "nonnegative": lambda v: v.is_nonnegative,
    "nonpositive": lambda v: v.is_nonpositive,
    "integer": lambda v: v.is_integer,
    "even": _even,
    "odd": _odd,
    "prime": lambda v: v.is_prime,
    "composite": lambda v: v.is_composite,
    "real": lambda v: v.is_real,
    "imaginary": lambda v: v.is_imaginary,
    "rational": lambda v: v.is_rational,
    "irrational": lambda v: v.is_irrational,
    "algebraic": lambda v: v.is_algebraic,
    "transcendental": lambda v: v.is_transcendental,
    "finite": lambda v: v.is_finite,
    "infinite": lambda v: v.is_infinite,
    "extended_real": lambda v: v.is_extended_real,
    "complex": lambda v: v.is_complex,
}


def _evaluate_boolean(expr: Any) -> bool | None:
    """Decide a Boolean expression whose atoms are concrete numbers.

    Uses numeric properties (``is_positive`` and friends) where possible and
    falls back to SymPy's ``ask`` for predicates without a numeric check.
    The equality oracle itself never uses ``ask``.
    """
    from sympy.assumptions.assume import AppliedPredicate
    from sympy.logic.boolalg import And, Not, Or

    if expr is S.true or expr is True:
        return True
    if expr is S.false or expr is False:
        return False
    if isinstance(expr, And):
        results = [_evaluate_boolean(arg) for arg in expr.args]
        if any(result is False for result in results):
            return False
        if all(result is True for result in results):
            return True
        return None
    if isinstance(expr, Or):
        results = [_evaluate_boolean(arg) for arg in expr.args]
        if any(result is True for result in results):
            return True
        if all(result is False for result in results):
            return False
        return None
    if isinstance(expr, Not):
        inner = _evaluate_boolean(expr.args[0])
        return None if inner is None else not inner
    if isinstance(expr, AppliedPredicate):
        name = getattr(expr.args[0], "name", None)
        arguments = expr.args[1:]
        check = _PREDICATE_CHECKS.get(name) if isinstance(name, str) else None
        if check is not None and len(arguments) == 1:
            result = check(arguments[0])
            if result is not None:
                return result
        if name in ("eq", "ne") and len(arguments) == 2:
            equal = simplify(arguments[0] - arguments[1]) == 0
            return bool(equal) if name == "eq" else not bool(equal)
    result = sympy_ask(expr)
    return result is S.true or result is True


def _sample_satisfies(assumptions: Any, sample: Mapping[Any, Any]) -> bool:
    if assumptions is True or assumptions is S.true:
        return True
    if assumptions is False or assumptions is S.false:
        return False
    if not hasattr(assumptions, "subs"):
        return False
    try:
        value = assumptions.subs(dict(sample))
    except Exception:
        return False
    return _evaluate_boolean(value) is True


def _numerically_equal(left: Any, right: Any) -> bool:
    try:
        left_value = left.evalf()
        right_value = right.evalf()
    except (TypeError, ValueError, OverflowError):
        return bool(simplify(left - right) == 0)
    if left_value.has(nan) or right_value.has(nan):
        return bool(left_value.has(nan) and right_value.has(nan))
    if left_value.has(zoo, oo, -oo) or right_value.has(zoo, oo, -oo):
        return bool(left_value == right_value)
    try:
        lv = complex(left_value)
        rv = complex(right_value)
    except (TypeError, ValueError, OverflowError):
        return bool(simplify(left - right) == 0)
    scale = max(1.0, abs(lv), abs(rv))
    return abs(lv - rv) <= 1e-9 * scale


def assert_refinement_valid(
    expr: Any,
    assumptions: Any,
    refined: Any,
    samples: int = 25,
    values: Mapping[Any, Sequence[Any]] | None = None,
) -> None:
    """Check ``refined`` against ``expr`` numerically under ``assumptions``.

    Draws up to ``samples`` tuples of values that satisfy ``assumptions``,
    substitutes them into both expressions, and requires agreement (with
    ``nan``/``zoo`` handled explicitly and ``simplify`` of the difference as a
    fallback for branch-cut-sensitive comparisons).  ``values`` overrides the
    candidate values of individual symbols, which is needed for assumptions
    such as ``Q.infinite`` that no finite default sample satisfies.
    """
    refined = sympify(refined)
    symbols = sorted(expr.free_symbols | refined.free_symbols, key=str)
    candidates: list[list[Any]] = []
    for symbol in symbols:
        if values is not None and symbol in values:
            candidates.append(list(values[symbol]))
        else:
            candidates.append(list(_DEFAULT_SAMPLES))

    checked = 0
    for sample_values in product(*candidates):
        sample = dict(zip(symbols, sample_values))
        if not _sample_satisfies(assumptions, sample):
            continue
        left = expr.subs(sample)
        right = refined.subs(sample)
        if not _numerically_equal(left, right):
            if simplify(left - right) != 0:
                raise AssertionError(
                    f"refinement {expr} -> {refined} is invalid at {sample}: "
                    f"{left} != {right}"
                )
        checked += 1
        if checked >= samples:
            return
    if checked == 0:
        raise AssertionError(
            f"no satisfying sample found for {assumptions!r}; pass values="
        )
