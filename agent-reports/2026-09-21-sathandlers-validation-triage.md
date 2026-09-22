# Agent report: would expanding sathandlers pass more validation tests?

- **Date:** 2026-09-21 (updated after the structural/function fact work landed on a branch)
- **Status:** investigation complete; number facts landed on `main`; a large part of the
  handler work now lives on branch **`agent/add-mul-pow-and-function-facts`** (pushed to
  the `bot` remote, `github.com/tilorc-bot/reasoning`), not yet on `main`
- **Scope:** `validation/test_query.py` + `validation/test_matrices.py` against pinned
  SymPy `ddbb536d` (1.15.0.dev)
- **Read this if:** you are editing `reasoning/sathandlers.py`, `reasoning/functionfacts.py`,
  `reasoning/numberfacts.py`, the known-facts import in `reasoning/sympy_adapter.py`, or
  trying to raise the validation pass rate. If you want to resume the handler work, start
  from the branch above.
- **Stale after:** any change to those fact modules, the comparison policy in
  `validation/compare_backends.py`, the SymPy pin, or the validation results
- **TL;DR:** `main` is at reasoning **40/104**, SymPy `satask` 24/104, full SymPy `ask`
  94/104. Branch `agent/add-mul-pow-and-function-facts` reaches **52/104** (18 matrix,
  12 handler tails, 2 old-assumption-flavored, 1 Symbol bridge and 9 non-handler
  failures left). "Expand sathandlers" is 3-4 commits; two of them (Add/Mul/Pow
  structural facts, elementary
  functions) are largely done on that branch, matrix facts are untouched.

## Where the work landed

Branch **`agent/add-mul-pow-and-function-facts`** on the `bot` remote (PR link:
`github.com/tilorc-bot/reasoning/pull/new/agent/add-mul-pow-and-function-facts`).

- `3840c36` + `82e4186`: Add/Mul/Pow structural facts and their tests (from worktree
  `/tmp/opencode/reasoning-2a`, branch `agent/2a-add-mul-pow`; the agent was cancelled
  after the code was complete but before it reported, so quality gates were run and
  the work committed manually).
- `fc0e6c6` + `3b34d49`: elementary-function facts and tests (worktree
  `/tmp/opencode/reasoning-2b`, branch `agent/2b-elementary-functions`).
- `cde5c70`: merge of the two, created in worktree `/tmp/opencode/reasoning-combined`
  (currently checked out there).

Gates on the merged branch: `pytest reasoning/tests` **95 passed, 1 xfailed**;
`mypy` strict clean; `tools/check_old_assumptions.py reasoning` 0 findings; both
validation suites **52 passed / 42 failed / 4 xfailed / 6 xpassed** (main: 40/54/8/2).

Merge notes for future agents:

- The merge conflict was only an import collision in `sathandlers.py`.
- A real interaction bug was fixed in the merge commit: the generic Pow rule
  `imaginary(exp) -> (real(expr) <=> imaginary(log(base)))` (copied from SymPy's
  `handlers/sets.py`) is wrong for base `E`, where the function facts handle realness
  exactly. Both fact sets derived `positive` and `~real` for `E**(I*pi*x)` with `even(x)`,
  which raised `ValueError: Inconsistent assumptions`. The rule is now restricted to
  non-`E` bases.
- `functionfacts.py` deliberately returns `~algebraic` rather than `transcendental`
  consequents (avoids a spurious UNSAT chain) and leaves `finite(log(x))` with
  `~zero(x)` as `None` instead of upstream's `True`.

## Remaining 42 failures on the branch by group

| Group | Count | Notes |
|---|---|---|
| Matrix expressions | 18 | 17 `test_matrices.py` tests plus `test_matrix`; untouched, largest remaining block |
| Handler tails | 12 | `test_I`, `complex`, `negative`, `rational`, `hermitian`, `imaginary`, `nonzero`, `real_pow` (structural tails) and `bounded`, `positive`, `real_functions`, `algebraic` (structural + function tails) |
| Old-assumption-flavored | 2 | `test_integer` (`integer(sqrt(2)*x)` -> False), `test_prime` (`prime(4*x)` -> False); upstream likely answers via old assumptions |
| Symbol old-assumption bridge | 1 | `test_check_old_assumption`; `tools/check_old_assumptions.py` flags exactly this |
| Non-handler / API | 9 | `context=` kwarg, `global_assumptions`, custom predicate/handler registration (4), relational predicates (2), `test_Add_queries` numeric evaluation |

Watch out: `test_hermitian` now over-answers at a later assertion (first failure moved
from `None is False` to `False is None`), so the structural tail needs an audit, not
just more facts.

## Findings that still hold

- The adapter imports SymPy's complete known predicate facts, so predicate-to-predicate
  relations are mostly not the gap. The encoding polarity in `_known_template` is
  correct; an apparent inversion was a false alarm about `Literal.is_Not` semantics.
- Not a propagation bug: the earlier `Q.hermitian(I)` mystery was missing facts (known
  facts carry `zero -> hermitian | antihermitian`, not the converse), now supplied by
  `numberfacts`.
- Handler work also requires curating the known-fact layer for clauses class facts
  cannot express (e.g. `hermitian & imaginary -> ~hermitian`; the branch adds such an
  extra-predicate-facts table in `sympy_adapter.py`).
- Full `ask` passes every test still failing here, so the suite itself is not the
  ceiling; the gap is the handler/old-assumption machinery `ask` has and `satask` does
  not.

## Next steps (the old "step 2" was too broad)

| Unit | Status | Remaining work | Test payoff |
|---|---|---|---|
| 2a. Add/Mul/Pow facts | mostly on branch; 10 of 18 targets flipped (plus 3 xfails now xpass) | structural tails above, `hermitian` over-inference audit, `integer`/`prime` may stay unreachable | ~8-10 |
| 2b. Elementary functions | on branch (`sin/cos/tan/cot/asin/acos/atan/acot/exp/log/Abs/re/im/factorial`); `test_issue_5833` and `test_issue_7246` fully pass | assertions still blocked on the 2a tails | ~3-5 additional |
| 2c. Matrix expressions | not started | ~20 matrix classes x ~15 predicates (invertible, fullrank, symmetric, orthogonal, unitary, positive_definite, triangular, diagonal, element sets, ...) | ~15-17 |
| 2d. Symbol old-assumption bridge | not started | read `Symbol('x', real=True)` etc.; flagged by the checker | 1 |

Calibration: `numberfacts` was ~320 fact lines plus ~270 test lines and netted 14
tests; the 2a+2b branch added roughly 900 lines and netted 12 more on top of `main`.
Tests are all-or-nothing, so a single missing rule keeps a whole test red; the payoffs
are per-unit ceilings, not additive guarantees. Projected total if 2a's tail, 2c and
2d land: **~73-79/104**.
